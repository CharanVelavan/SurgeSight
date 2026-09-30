/** Builds the alert field for a valid time and renders it as a smooth zone image. Called at most once per hour of timeline time. */

import { sampleRain, sampleWind } from '@/weather/atlas'
import { rainField, windField, type RainSource } from '@/weather/field'
import type { Manifest } from '@/weather/manifest'
import { RAIN_CUTS, WIND_CUTS, severity, stormWindKmh, type StormState } from './zones'

export const ZONE_COLORS: readonly [number, number, number, number][] = [
  [63, 178, 127, 40],
  [232, 197, 71, 110],
  [240, 138, 36, 130],
  [229, 72, 77, 150],
]
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

/** Bilinear upsample of the severity, then hard colour bands: the zone edges are smooth contours, not grid squares. */
export function renderZones(sev: Float32Array, W: number, H: number, scale = 3): ImageData {
  const w = W * scale, h = H * scale
  const img = new ImageData(w, h)
  for (let py = 0; py < h; py++) {
    const fy = Math.min(Math.max((py + 0.5) / scale - 0.5, 0), H - 1)
    const y0 = Math.floor(fy), y1 = Math.min(y0 + 1, H - 1), ty = fy - y0
    for (let px = 0; px < w; px++) {
      const fx = Math.min(Math.max((px + 0.5) / scale - 0.5, 0), W - 1)
      const x0 = Math.floor(fx), x1 = Math.min(x0 + 1, W - 1), tx = fx - x0
      const top = sev[y0 * W + x0] * (1 - tx) + sev[y0 * W + x1] * tx
      const bottom = sev[y1 * W + x0] * (1 - tx) + sev[y1 * W + x1] * tx
      const level = Math.min(3, Math.floor(top * (1 - ty) + bottom * ty))
      const c = ZONE_COLORS[level]
      const o = (py * w + px) * 4
      img.data[o] = c[0]
      img.data[o + 1] = c[1]
      img.data[o + 2] = c[2]
      img.data[o + 3] = c[3]
    }
  }
  return img
}
