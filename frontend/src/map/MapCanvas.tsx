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
import { INDIA, IMPACT, IMPACT_LIMIT, easeInOutCubic, fitCamera, nationalBox } from './view'
import { currentLang } from '@/i18n'
import { setMapFailed } from '@/lib/net'
import { useResolvedTheme } from '@/app/prefs'
import { useT } from '@/i18n'
import { Minus, Plus } from 'lucide-react'
import { recordFrame } from './quality'

const API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined
// DEMO_MAP_ID is Google's vector demo style; set VITE_GOOGLE_MAP_ID to the project's own Map ID.
const MAP_ID = (import.meta.env.VITE_GOOGLE_MAP_ID as string | undefined) || 'DEMO_MAP_ID'

const MAP_TYPE: Record<Basemap, string> = { dark: 'roadmap', satellite: 'hybrid', terrain: 'terrain' }

/** Frames the view and lets the user zoom and pan freely, but only inside the national boundary (or the impact limit). */
function ViewController() {
  const map = useMap()
  const view = useUi(s => s.view)

  // Frame the view. The minimum zoom is the frame itself, so the map can never leave the boundary.
  useEffect(() => {
    if (!map) return
    const div = map.getDiv()
    const apply = () => {
      const w = div.clientWidth, h = div.clientHeight
      if (!w || !h) return
      const cam = fitCamera(view === 'india' ? nationalBox(w, h) : IMPACT, w, h)
      map.setOptions({ restriction: null, minZoom: 1, maxZoom: 21 })
      map.moveCamera({ center: cam.center, zoom: cam.zoom })
      // A strict limit made Google settle on a whole zoom (5 instead of the exact frame), so only the centre is kept inside.
      const limit = view === 'india' ? INDIA : IMPACT_LIMIT
      map.setOptions({
        gestureHandling: 'greedy',
        keyboardShortcuts: false,
        minZoom: cam.zoom,
        maxZoom: view === 'india' ? 12 : 15,
        restriction: { latLngBounds: { north: limit.north, south: limit.south, west: limit.west, east: limit.east }, strictBounds: false },
      })
      // Google can settle on a whole zoom during the first pass; moving again puts the camera on the exact frame.
      for (const ms of [0, 400, 1200]) setTimeout(() => map.getZoom() !== cam.zoom && map.moveCamera({ center: cam.center, zoom: cam.zoom }), ms)
      useUi.getState().set({ zoom: cam.zoom })
    }
    apply()
    const idle = google.maps.event.addListenerOnce(map, 'idle', apply)
    const ro = new ResizeObserver(apply)
    ro.observe(div)
    const zl = map.addListener('zoom_changed', () => useUi.getState().set({ zoom: map.getZoom() ?? 4 }))
    return () => {
      ro.disconnect()
      idle.remove()
      zl.remove()
    }
  }, [map, view])

  // Fly to a point on request (lists, "Show on map"). A request made before the map existed is served once it is ready.
  useEffect(() => {
    if (!map) return
    const fly = (f: { lon: number; lat: number; zoom: number }) => {
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
    }
    const pending = setTimeout(() => {
      const f = useUi.getState().focus
      if (f) fly(f)
    }, 700)
    const unsub = useUi.subscribe((s, prev) => {
      if (s.focus && s.focus !== prev.focus) fly(s.focus)
    })
    return () => {
      clearTimeout(pending)
      unsub()
    }
  }, [map])

  return null
}

/** Zoom buttons for keyboard and touch users; the map itself has its default controls turned off. */
function ZoomButtons() {
  const map = useMap()
  const t = useT()
  const step = (d: number) => map && map.setZoom((map.getZoom() ?? 5) + d)
  const cls = 'grid size-9 place-items-center text-foreground transition-colors hover:bg-accent'
  return (
    <div className="panel absolute top-16 left-3 z-10 flex flex-col overflow-hidden p-0">
      <button type="button" onClick={() => step(1)} aria-label={t('map.zoomIn')} className={cls}><Plus className="size-4" /></button>
      <span className="h-px bg-border" />
      <button type="button" onClick={() => step(-1)} aria-label={t('map.zoomOut')} className={cls}><Minus className="size-4" /></button>
    </div>
  )
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
  const theme = useResolvedTheme()
  if (!API_KEY) {
    return (
      <div className="grid h-full place-items-center text-sm text-muted-foreground">
        Set VITE_GOOGLE_MAPS_API_KEY in the repo-root .env to load the map.
      </div>
    )
  }
  return (
    <APIProvider apiKey={API_KEY} language={currentLang()} onError={() => setMapFailed()}>
      <Map
        key={theme}
        className="absolute inset-0"
        mapId={MAP_ID}
        colorScheme={theme === 'dark' ? 'DARK' : 'LIGHT'}
        renderingType="VECTOR"
        defaultCenter={{ lat: 19, lng: 78 }}
        defaultZoom={4.7}
        gestureHandling="none"
        disableDefaultUI
        clickableIcons={false}
      >
        <ViewController />
        <DeckOverlay />
        <ZoomButtons />
      </Map>
    </APIProvider>
  )
}
