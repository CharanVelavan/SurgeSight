/**
 * Alert zones: one level per place from wind and rain, using the thresholds shared with the backend
 * (config/alert_thresholds.json). Near a cyclone the wind is the larger of the GFS wind and a Holland (1980)
 * profile around the storm centre, because 0.25 degree GFS winds underestimate a cyclone's core.
 * These are SurgeSight screening levels, not an IMD warning.
 */

import thresholds from '@config/alert_thresholds.json'

export const LEVELS = thresholds.levels as readonly string[]
export const WIND_CUTS = thresholds.wind_kmh
export const RAIN_CUTS = thresholds.rain_mm_h
export const ZONE_LABEL = thresholds.label

/** Continuous severity: floor() is the level (0 green .. 3 red), the fraction is progress to the next cut. */
export function severity(v: number, cuts: readonly number[]): number {
  let i = 0
  while (i < cuts.length && v >= cuts[i]) i++
  if (i === cuts.length) return 3.5
  const lower = i === 0 ? 0 : cuts[i - 1]
  return i + ((v - lower) / (cuts[i] - lower)) * 0.999
}

export const alertLevel = (windKmh: number, rainMmH: number): number =>
  Math.max(WIND_CUTS.filter(c => windKmh >= c).length, RAIN_CUTS.filter(c => rainMmH >= c).length)

export interface StormState {
  lat: number
  lon: number
  vmaxKmh: number
  /** Translation speed (km/h) and heading (degrees clockwise from north); 0 speed when unknown. */
  speedKmh: number
  headingDeg: number
}

const R_EARTH = 6371.0088
const rad = (d: number) => (d * Math.PI) / 180

export function distanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const dLat = rad(lat2 - lat1), dLon = rad(lon2 - lon1)
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLon / 2) ** 2
  return 2 * R_EARTH * Math.asin(Math.min(1, Math.sqrt(a)))
}

export function bearingDeg(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const dLon = rad(lon2 - lon1)
  const y = Math.sin(dLon) * Math.cos(rad(lat2))
  const x = Math.cos(rad(lat1)) * Math.sin(rad(lat2)) - Math.sin(rad(lat1)) * Math.cos(rad(lat2)) * Math.cos(dLon)
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360
}

/** Willoughby et al. (2006) radius of maximum wind, as in services/hazards/wind_field.py. */
export const rmwKm = (vmaxMs: number, lat: number) => 46.4 * Math.exp(-0.0155 * vmaxMs + 0.0169 * Math.abs(lat))

export function hollandKmh(rKm: number, vmaxKmh: number, rmaxKm: number, b = 1.5): number {
  const x = (rmaxKm / Math.max(rKm, 1)) ** b
  return vmaxKmh * Math.sqrt(x * Math.exp(1 - x))
}

/** Holland wind with the same right-of-track asymmetry as the backend. */
export function stormWindKmh(s: StormState, lat: number, lon: number): number {
  const r = distanceKm(s.lat, s.lon, lat, lon)
  const w = hollandKmh(r, s.vmaxKmh, rmwKm(s.vmaxKmh / 3.6, s.lat))
  if (s.speedKmh <= 0) return w
  const alpha = rad(bearingDeg(s.lat, s.lon, lat, lon) - s.headingDeg)
  return Math.max(w + 0.5 * s.speedKmh * Math.sin(alpha), 0)
}
