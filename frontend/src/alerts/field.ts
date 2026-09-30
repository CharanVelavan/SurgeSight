/** Builds the alert field for a valid time and renders it as a smooth zone image. Called at most once per hour of timeline time. */

import { sampleRain, sampleWind } from '@/weather/atlas'
import { rainField, windField, type RainSource } from '@/weather/field'
import type { Manifest } from '@/weather/manifest'
import { RAIN_CUTS, WIND_CUTS, severity, stormWindKmh, type StormState } from './zones'

/** Zone colours per level (0 is left clear on the map). */
export const ZONE_HEX = ['#3FB27F', '#E8C547', '#F08A24', '#E5484D']
/** Severity per grid node, row-major from the north-west corner. */
export function alertField(m: Manifest, time: number, cutoff: number, rainSource: RainSource, storm: StormState | null): Float32Array {
  const { west, north, step } = m.bounds
  const { width: W, height: H } = m.tile
  const out = new Float32Array(W * H)
  const wp = windField(m, time, cutoff)
  const rp = rainField(m, time, cutoff, rainSource)
  for (let y = 0; y < H; y++) {
    const lat = north - y * step
    for (let x = 0; x < W; x++) {
      const lon = west + x * step
      let wind = 0
      if (wp) {
        const w = sampleWind(wp, m, lon, lat)
        if (w) wind = Math.hypot(w.u, w.v) * 3.6
      }
      if (storm) wind = Math.max(wind, stormWindKmh(storm, lat, lon))
      const rain = rp ? (sampleRain(rp, m, lon, lat) ?? 0) : 0
      out[y * W + x] = Math.max(severity(wind, WIND_CUTS), severity(rain, RAIN_CUTS))
    }
  }
  return out
}
