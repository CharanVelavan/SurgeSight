/** Where the storm is at a valid time, without hindsight: observed up to the cutoff, our experimental forecast after it. */

import type { ExperimentalForecast, TrackPoint } from '@/lib/api'
import { trackAt } from '@/lib/imd'
import { bearingDeg, distanceKm, type StormState } from './zones'

const KT_TO_KMH = 1.852
const HALF_STEP = 90 * 60_000

type Fix = { lat: number; lon: number }

function forecastAt(points: ExperimentalForecast['data']['models']['wind_informed_kalman']['forecast'], ms: number): Fix | null {
  if (points.length < 2) return null
  const t = points.map(p => Date.parse(p.timestamp))
  if (ms < t[0] || ms > t[t.length - 1]) return null
  const j = t.findIndex(x => x >= ms)
  const i = Math.max(j - 1, 0)
  const f = t[j] === t[i] ? 0 : (ms - t[i]) / (t[j] - t[i])
  return { lat: points[i].lat + (points[j].lat - points[i].lat) * f, lon: points[i].lon + (points[j].lon - points[i].lon) * f }
}

export function stormAt(
  track: TrackPoint[] | undefined,
  forecast: ExperimentalForecast['data'] | null,
  time: number,
  cutoff: number,
): StormState | null {
  if (!track?.length) return null
  const fix = (ms: number): Fix | null => {
    if (ms <= cutoff) return trackAt(track, ms)
    const pts = forecast?.models.wind_informed_kalman?.forecast
    return pts ? forecastAt(pts, ms) : null
  }
  const here = fix(time)
  const anchor = trackAt(track, Math.min(time, cutoff))
  if (!here || !anchor) return null
  // Intensity after the cutoff is held at the last observation: the forecast has no intensity.
  const vmaxKmh = anchor.wind_kt * KT_TO_KMH
  const a = fix(time - HALF_STEP) ?? here
  const b = fix(time + HALF_STEP) ?? here
  const km = distanceKm(a.lat, a.lon, b.lat, b.lon)
  const hours = (fix(time - HALF_STEP) && fix(time + HALF_STEP) ? 2 * HALF_STEP : HALF_STEP) / 3_600_000
  return {
    lat: here.lat,
    lon: here.lon,
    vmaxKmh,
    speedKmh: km / hours,
    headingDeg: km > 0 ? bearingDeg(a.lat, a.lon, b.lat, b.lon) : 0,
  }
}
