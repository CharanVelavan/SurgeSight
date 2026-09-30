/** IMD cyclone classification by maximum sustained wind (knots) and interpolation along the track. */

import type { TrackPoint } from './api'

const CLASSES: [number, string, string][] = [
  [120, 'SuCS', 'Super Cyclonic Storm'],
  [90, 'ESCS', 'Extremely Severe Cyclonic Storm'],
  [64, 'VSCS', 'Very Severe Cyclonic Storm'],
  [48, 'SCS', 'Severe Cyclonic Storm'],
  [34, 'CS', 'Cyclonic Storm'],
  [28, 'DD', 'Deep Depression'],
  [17, 'D', 'Depression'],
  [0, 'LPA', 'Low Pressure Area'],
]

export function imdClass(kt: number): { short: string; long: string } {
  const [, short, long] = CLASSES.find(([min]) => kt >= min) ?? CLASSES[CLASSES.length - 1]
  return { short, long }
}

/** Track state at a time, linearly interpolated; null outside the observed track. */
export function trackAt(track: TrackPoint[], ms: number): TrackPoint | null {
  if (!track.length) return null
  const t0 = Date.parse(track[0].time)
  if (ms < t0 || ms > Date.parse(track[track.length - 1].time)) return null
  for (let i = 1; i < track.length; i++) {
    const b = Date.parse(track[i].time)
    if (ms <= b) {
      const a = Date.parse(track[i - 1].time)
      const f = b === a ? 0 : (ms - a) / (b - a)
      const p = track[i - 1], q = track[i]
      return {
        time: new Date(ms).toISOString(),
        lat: p.lat + (q.lat - p.lat) * f,
        lon: p.lon + (q.lon - p.lon) * f,
        wind_kt: p.wind_kt + (q.wind_kt - p.wind_kt) * f,
        pressure_hpa: p.pressure_hpa + (q.pressure_hpa - p.pressure_hpa) * f,
      }
    }
  }
  return track[track.length - 1]
}
