/** Keeps the latest zone image for the frame loop, recomputing when the valid time moves an hour or an input changes. */

import { alertField } from './field'
import { encodeSeverity } from '@/layers/zones/ZoneLayer'
import type { StormState } from './zones'
import type { Manifest } from '@/weather/manifest'
import type { RainSource } from '@/weather/field'

const STEP_MS = 60 * 60_000
let key = ''
let bitmap: ImageBitmap | null = null
let pending = false

export function zoneImage(m: Manifest, time: number, cutoff: number, rainSource: RainSource, storm: StormState | null): ImageBitmap | null {
  const k = [Math.round(time / STEP_MS), cutoff, rainSource, storm ? `${storm.lat.toFixed(2)},${storm.lon.toFixed(2)},${Math.round(storm.vmaxKmh)}` : '-'].join('|')
  if (k !== key && !pending) {
    key = k
    pending = true
    const t0 = performance.now()
    const img = encodeSeverity(alertField(m, time, cutoff, rainSource, storm), m.tile.width, m.tile.height)
    if (import.meta.env.DEV) (window as unknown as { __zoneMs: number }).__zoneMs = performance.now() - t0
    createImageBitmap(img, { premultiplyAlpha: 'none', colorSpaceConversion: 'none' }).then(b => {
      bitmap?.close()
      bitmap = b
      pending = false
    })
  }
  return bitmap
}
