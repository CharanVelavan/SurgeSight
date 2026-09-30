/**
 * Full-bleed Google vector map with deck.gl interleaved into its WebGL context. Raster basemaps (where
 * the map cannot share its context) fall back to a synced deck canvas on top: the S0 decision, made at
 * runtime from the map's rendering type.
 */

import { useEffect, useRef } from 'react'
import { APIProvider, Map, useMap } from '@vis.gl/react-google-maps'
import { SurgeMapsOverlay } from './overlay'
import { useUi, type Basemap } from '@/state/ui'
import { onFrame } from '@/timeline/clock'
import { buildLayers } from './layers'
import { recordFrame } from './quality'

const API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined
// DEMO_MAP_ID is Google's vector demo style; set VITE_GOOGLE_MAP_ID to the project's own Map ID.
const MAP_ID = (import.meta.env.VITE_GOOGLE_MAP_ID as string | undefined) || 'DEMO_MAP_ID'

const MAP_TYPE: Record<Basemap, string> = { dark: 'roadmap', satellite: 'hybrid', terrain: 'terrain' }

function DeckOverlay() {
  const map = useMap()
  const basemap = useUi(s => s.basemap)
  const overlayRef = useRef<SurgeMapsOverlay | null>(null)

  // (Re)create the overlay whenever the rendering type changes: interleaved needs a vector map.
  useEffect(() => {
    if (!map) return
    const attach = () => {
      const vector = map.getRenderingType() === google.maps.RenderingType.VECTOR
      overlayRef.current?.finalize()
      const overlay = new SurgeMapsOverlay({ interleaved: vector, layers: [], onError: err => console.error('[deck]', err) })
      overlay.setMap(map)
      overlayRef.current = overlay
      if (import.meta.env.DEV) (window as unknown as { __overlay: unknown }).__overlay = overlay
      document.documentElement.dataset.renderingType = vector ? 'vector-interleaved' : 'raster-overlay'
    }
    const listener = map.addListener('renderingtype_changed', attach)
    if (map.getRenderingType() !== google.maps.RenderingType.UNINITIALIZED) attach()
    return () => {
      listener.remove()
      overlayRef.current?.finalize()
      overlayRef.current = null
    }
  }, [map])

  useEffect(() => {
    map?.setMapTypeId(MAP_TYPE[basemap])
  }, [map, basemap])

  // One frame loop drives the layers; React is not involved per frame.
  useEffect(
    () =>
      onFrame((now, dt) => {
        recordFrame(now, dt)
        overlayRef.current?.setProps({ layers: buildLayers(now) })
      }),
    [],
  )

  // Cursor position for the readout, coalesced to one update per frame.
  useEffect(() => {
    if (!map) return
    let raf = 0
    let latest: google.maps.MapMouseEvent | null = null
    const move = map.addListener('mousemove', (e: google.maps.MapMouseEvent) => {
      latest = e
      if (!raf)
        raf = requestAnimationFrame(() => {
          raf = 0
          const ev = latest?.domEvent as MouseEvent | undefined
          if (latest?.latLng && ev)
            useUi.getState().set({ cursor: { lon: latest.latLng.lng(), lat: latest.latLng.lat(), x: ev.clientX, y: ev.clientY } })
        })
    })
    const out = map.addListener('mouseout', () => useUi.getState().set({ cursor: null }))
    return () => {
      move.remove()
      out.remove()
      cancelAnimationFrame(raf)
    }
  }, [map])

  return null
}

export function MapCanvas() {
  if (!API_KEY) {
    return (
      <div className="grid h-full place-items-center text-sm text-muted-foreground">
        Set VITE_GOOGLE_MAPS_API_KEY in the repo-root .env to load the map.
      </div>
    )
  }
  return (
    <APIProvider apiKey={API_KEY}>
      <Map
        className="absolute inset-0"
        mapId={MAP_ID}
        colorScheme="DARK"
        renderingType="VECTOR"
        defaultCenter={{ lat: 13.5, lng: 84 }}
        defaultZoom={5.3}
        minZoom={4}
        maxZoom={12}
        gestureHandling="greedy"
        disableDefaultUI
        clickableIcons={false}
        restriction={{ latLngBounds: { north: 32, south: -8, west: 60, east: 112 }, strictBounds: false }}
      >
        <DeckOverlay />
      </Map>
    </APIProvider>
  )
}
