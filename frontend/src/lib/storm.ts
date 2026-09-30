/** The storm as it stood at a bulletin time: intensity, motion and when it reaches (or reached) the coast. */

import type { Timeline } from './api'
import { imdClass, trackAt } from './imd'

const R = 6371.0088
const rad = (d: number) => (d * Math.PI) / 180

export interface StormStatus {
  lat: number
  lon: number
  windKmh: number
  pressure: number
  cls: { short: string; long: string }
  /** Heading (degrees clockwise from north) and speed over the previous 6 h, when known. */
  headingDeg: number | null
  speedKmh: number | null
  /** Hours from the bulletin to the first observed point over land: positive ahead, negative after. */
  landfallInH: number | null
}

export function stormStatus(tl: Timeline, cutoff: number): StormStatus | null {
  const p = trackAt(tl.track, cutoff)
  if (!p) return null
  const q = trackAt(tl.track, cutoff - 6 * 3_600_000)
  let headingDeg: number | null = null
  let speedKmh: number | null = null
  if (q) {
    const dLat = rad(p.lat - q.lat), dLon = rad(p.lon - q.lon)
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(rad(q.lat)) * Math.cos(rad(p.lat)) * Math.sin(dLon / 2) ** 2
    speedKmh = (2 * R * Math.asin(Math.sqrt(a))) / 6
    const y = Math.sin(dLon) * Math.cos(rad(p.lat))
    const x = Math.cos(rad(q.lat)) * Math.sin(rad(p.lat)) - Math.sin(rad(q.lat)) * Math.cos(rad(p.lat)) * Math.cos(dLon)
    headingDeg = ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360
  }
  const land = tl.first_over_land ? Date.parse(tl.first_over_land.time) : null
  return {
    lat: p.lat,
    lon: p.lon,
    windKmh: p.wind_kt * 1.852,
    pressure: p.pressure_hpa,
    cls: imdClass(p.wind_kt),
    headingDeg,
    speedKmh,
    landfallInH: land === null ? null : Math.round((land - cutoff) / 3_600_000),
  }
}
