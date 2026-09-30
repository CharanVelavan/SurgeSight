/** Storm track, experimental forecast and uncertainty circles. Data arrays are memoised per key. */

import type { Layer } from '@deck.gl/core'
import { PathStyleExtension } from '@deck.gl/extensions'
import { PathLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers'
import { trackStore } from '@/data/track'
import { hexToRgb } from '@/lib/colors'
import type { ForecastPoint, Timeline } from '@/lib/api'
import { trackAt } from '@/lib/imd'
import { useUi } from '@/state/ui'
import { clock } from '@/timeline/clock'

type Pt = [number, number]

const PRIMARY = hexToRgb('#7FA7D9')
const AMBER = hexToRgb('#E0B34A')
const GREY = hexToRgb('#8B939D')
const dash = new PathStyleExtension({ dash: true })

interface Memo<T> { key: string; value: T }
const memo = <T,>(m: { current: Memo<T> | null }, key: string, make: () => T): T => {
  if (m.current?.key !== key) m.current = { key, value: make() }
  return m.current.value
}

const observedMemo: { current: Memo<{ path: Pt[]; dots: Pt[] }> | null } = { current: null }
const ghostMemo: { current: Memo<Pt[]> | null } = { current: null }

/** Track positions up to `untilMs`, ending on the interpolated position at that time. */
function pathUntil(t: Timeline, untilMs: number): { path: Pt[]; dots: Pt[] } {
  const dots: Pt[] = []
  const path: Pt[] = []
  for (const p of t.track) {
    if (Date.parse(p.time) > untilMs) break
    dots.push([p.lon, p.lat])
    path.push([p.lon, p.lat])
  }
  const end = trackAt(t.track, untilMs)
  if (end && (!path.length || path[path.length - 1][0] !== end.lon || path[path.length - 1][1] !== end.lat)) path.push([end.lon, end.lat])
  return { path, dots }
}

/** Track from one time to another: interpolated start, the fixes in between, interpolated end. */
function segment(t: Timeline, fromMs: number, toMs: number): Pt[] {
  const pts: Pt[] = []
  const a = trackAt(t.track, fromMs)
  if (a) pts.push([a.lon, a.lat])
  for (const p of t.track) {
    const ms = Date.parse(p.time)
    if (ms > fromMs && ms < toMs) pts.push([p.lon, p.lat])
  }
  const b = trackAt(t.track, toMs)
  if (b) pts.push([b.lon, b.lat])
  return pts
}

const HOUR_BUCKET = 15 * 60_000

export function buildTrackLayers(): Layer[] {
  const { timeline, forecast } = trackStore.getState()
  if (!timeline) return []
  const { time, cutoff } = clock.getState()
  const ui = useUi.getState()
  const layers: Layer[] = []

  // Observed past: knowable, so limited to the cutoff.
  const until = Math.min(time, cutoff)
  const bucket = Math.floor(until / HOUR_BUCKET)
  const obs = memo(observedMemo, `${timeline.start}|${bucket}`, () => pathUntil(timeline, bucket * HOUR_BUCKET))
  if (obs.path.length > 1) {
    layers.push(
      new PathLayer({ id: 'track-observed', data: [{ path: obs.path }], getPath: d => d.path, getColor: [...PRIMARY, 235], getWidth: 2.5, widthUnits: 'pixels', capRounded: true, jointRounded: true }),
      new ScatterplotLayer({ id: 'track-observed-dots', data: obs.dots, getPosition: d => d, getFillColor: [...PRIMARY, 255], getRadius: 3.2, radiusUnits: 'pixels' }),
    )
  }

  // What actually happened after the cutoff: only with the validation toggle, and drawn faint.
  if (ui.rainSource === 'observed' && time > cutoff) {
    const gb = Math.floor(time / HOUR_BUCKET)
    const ghost = memo(ghostMemo, `${timeline.start}|${cutoff}|${gb}`, () => segment(timeline, cutoff, gb * HOUR_BUCKET))
    if (ghost.length > 1)
      layers.push(new PathLayer({ id: 'track-validation', data: [{ path: ghost }], getPath: d => d.path, getColor: [...PRIMARY, 110], getWidth: 2, widthUnits: 'pixels', getDashArray: [4, 3], dashJustified: true, extensions: [dash] }))
  }

  // Storm position at the valid time (drawn while it is knowable at the cutoff).
  const here = trackAt(timeline.track, Math.min(time, ui.rainSource === 'observed' ? time : cutoff))
  if (here) {
    layers.push(new ScatterplotLayer({
      id: 'storm', data: [here], getPosition: d => [d.lon, d.lat], getRadius: 8, radiusUnits: 'pixels',
      getFillColor: [11, 13, 16, 255], getLineColor: [...PRIMARY, 255], stroked: true, getLineWidth: 2.5, lineWidthUnits: 'pixels',
    }))
  }

  // Experimental forecast issued at the cutoff: both models, circles for the better one.
  if (forecast) {
    const start = trackAt(timeline.track, cutoff)
    const model = (key: 'position_only_kalman' | 'wind_informed_kalman') => forecast.models[key]?.forecast ?? []
    const wind = model('wind_informed_kalman')
    const pos = model('position_only_kalman')
    const line = (pts: ForecastPoint[]) => [...(start ? [[start.lon, start.lat] as Pt] : []), ...pts.map(p => [p.lon, p.lat] as Pt)]
    if (wind.length)
      layers.push(
        new ScatterplotLayer({
          id: 'forecast-uncertainty', data: wind, getPosition: d => [d.lon, d.lat], getRadius: d => d.uncertainty_radius_km * 1000, radiusUnits: 'meters',
          getFillColor: [...AMBER, 22], stroked: true, getLineColor: [...AMBER, 120], getLineWidth: 1, lineWidthUnits: 'pixels',
        }),
      )
    if (pos.length)
      layers.push(new PathLayer({ id: 'forecast-position', data: [{ path: line(pos) }], getPath: d => d.path, getColor: [...GREY, 200], getWidth: 1.5, widthUnits: 'pixels', getDashArray: [5, 4], dashJustified: true, extensions: [dash] }))
    if (wind.length)
      layers.push(
        new PathLayer({ id: 'forecast-wind', data: [{ path: line(wind) }], getPath: d => d.path, getColor: [...AMBER, 240], getWidth: 2.5, widthUnits: 'pixels', getDashArray: [5, 3], dashJustified: true, extensions: [dash] }),
        new ScatterplotLayer({ id: 'forecast-dots', data: wind, getPosition: d => [d.lon, d.lat], getFillColor: [...AMBER, 255], getRadius: 3.5, radiusUnits: 'pixels' }),
        new TextLayer({
          id: 'forecast-labels', data: wind, getPosition: d => [d.lon, d.lat], getText: d => `+${d.lead_hours} h`, getSize: 11, sizeUnits: 'pixels',
          getColor: [...AMBER, 255], getPixelOffset: [0, -14], fontFamily: 'Geist Mono Variable, ui-monospace, monospace', background: false, outlineWidth: 3, outlineColor: [11, 13, 16, 220],
          fontSettings: { sdf: true }, characterSet: '+0123456789 h',
        }),
      )
  }
  return layers
}
