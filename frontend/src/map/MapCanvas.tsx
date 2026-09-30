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
import { INTRO_MS, IMPACT, IMPACT_LIMIT, INDIA, easeInOutCubic, fitCamera, introSeen, markIntroSeen } from './view'
import { recordFrame } from './quality'

const API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined
// DEMO_MAP_ID is Google's vector demo style; set VITE_GOOGLE_MAP_ID to the project's own Map ID.
const MAP_ID = (import.meta.env.VITE_GOOGLE_MAP_ID as string | undefined) || 'DEMO_MAP_ID'

const MAP_TYPE: Record<Basemap, string> = { dark: 'roadmap', satellite: 'hybrid', terrain: 'terrain' }

/** Holds the camera on a fixed frame: locked on India, pannable only inside the impact area. */
function ViewController() {
  const map = useMap()
  const view = useUi(s => s.view)

  // Opening fly-in: once per session, skippable, never with reduced motion.
  useEffect(() => {
    if (!map || introSeen()) return
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
      markIntroSeen()
      return
    }
    const div = map.getDiv()
    const to = fitCamera(INDIA, div.clientWidth, div.clientHeight)
    const from = { lat: 24, lng: 80, zoom: Math.max(2, to.zoom - 2.4) }
    useUi.getState().set({ intro: true })
    map.setOptions({ restriction: null, minZoom: 1, maxZoom: 21, gestureHandling: 'none' })
    map.moveCamera({ center: { lat: from.lat, lng: from.lng }, zoom: from.zoom })
    const t0 = performance.now()
    let raf = 0
    const finish = () => {
      markIntroSeen()
      cancelAnimationFrame(raf)
      window.removeEventListener('pointerdown', finish)
      window.removeEventListener('keydown', finish)
      map.moveCamera({ center: to.center, zoom: to.zoom })
      map.setOptions({ minZoom: to.zoom, maxZoom: to.zoom })
      useUi.getState().set({ intro: false, zoom: to.zoom })
    }
    const frame = (now: number) => {
      const t = Math.min(1, (now - t0) / INTRO_MS)
      const e = easeInOutCubic(t)
      map.moveCamera({ center: { lat: from.lat + (to.center.lat - from.lat) * e, lng: from.lng + (to.center.lng - from.lng) * e }, zoom: from.zoom + (to.zoom - from.zoom) * e })
      if (t < 1) raf = requestAnimationFrame(frame)
      else finish()
    }
    raf = requestAnimationFrame(frame)
    window.addEventListener('pointerdown', finish)
    window.addEventListener('keydown', finish)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('pointerdown', finish)
      window.removeEventListener('keydown', finish)
    }
  }, [map])

  // Frame the view; locked on India, pannable only inside the impact area.
  useEffect(() => {
    if (!map) return
    const div = map.getDiv()
    const apply = () => {
      if (useUi.getState().intro) return
      const w = div.clientWidth, h = div.clientHeight
      if (!w || !h) return
      const cam = fitCamera(view === 'india' ? INDIA : IMPACT, w, h)
      map.setOptions({ restriction: null, minZoom: 1, maxZoom: 21 })
      map.moveCamera({ center: cam.center, zoom: cam.zoom })
      map.setOptions(
        view === 'india'
          ? { gestureHandling: 'none', keyboardShortcuts: false, minZoom: cam.zoom, maxZoom: cam.zoom }
          : {
              gestureHandling: 'greedy',
              keyboardShortcuts: false,
              minZoom: cam.zoom,
              maxZoom: 15,
              restriction: { latLngBounds: { north: IMPACT_LIMIT.north, south: IMPACT_LIMIT.south, west: IMPACT_LIMIT.west, east: IMPACT_LIMIT.east }, strictBounds: false },
            },
      )
      useUi.getState().set({ zoom: cam.zoom })
    }
    apply()
    const ro = new ResizeObserver(apply)
    ro.observe(div)
    const zl = map.addListener('zoom_changed', () => {
      if (!useUi.getState().intro) useUi.getState().set({ zoom: map.getZoom() ?? 4 })
    })
    const unsub = useUi.subscribe((s, prev) => {
      if (prev.intro && !s.intro) apply()
    })
    return () => {
      ro.disconnect()
      zl.remove()
      unsub()
    }
  }, [map, view])

  // Fly to a point on request (the summary list), staying inside the impact area.
  useEffect(
    () =>
      useUi.subscribe((s, prev) => {
        const f = s.focus
        if (!map || !f || f === prev.focus) return
        useUi.getState().set({ focus: null })
        const c = map.getCenter()
        if (!c) return
        const from = { lat: c.lat(), lng: c.lng(), zoom: map.getZoom() ?? f.zoom }
        const t0 = performance.now()
        const frame = (now: number) => {
          const t = Math.min(1, (now - t0) / 900)
          const e = easeInOutCubic(t)
          map.moveCamera({ center: { lat: from.lat + (f.lat - from.lat) * e, lng: from.lng + (f.lon - from.lng) * e }, zoom: from.zoom + (f.zoom - from.zoom) * e })
          if (t < 1) requestAnimationFrame(frame)
        }
        requestAnimationFrame(frame)
      }),
    [map],
  )

  return null
}

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
        defaultCenter={{ lat: 19, lng: 78 }}
        defaultZoom={4.7}
        gestureHandling="none"
        disableDefaultUI
        clickableIcons={false}
      >
        <ViewController />
        <DeckOverlay />
      </Map>
    </APIProvider>
  )
}
