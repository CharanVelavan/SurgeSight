/** Builds the deck.gl layer list for one animation frame from the clock, the weather store and the UI. */

import type { Layer } from '@deck.gl/core'
import { useUi } from '@/state/ui'
import { clock } from '@/timeline/clock'
import { weatherStore } from '@/weather/atlas'
import { rainField, tileRect, windField } from '@/weather/field'
import { RainLayer } from '@/layers/rain/RainLayer'
import { WindParticleLayer } from '@/layers/wind/WindParticleLayer'
import { buildAssetLayers } from './assetLayers'
import { quality } from './quality'

type Vec4 = [number, number, number, number]

let bitmapList: ImageBitmap[] = []
let bitmapSource: unknown = null
function bitmaps(atlases: Map<string, { bitmap: ImageBitmap }>): ImageBitmap[] {
  if (atlases !== bitmapSource) {
    bitmapSource = atlases
    bitmapList = [...atlases.values()].map(a => a.bitmap)
  }
  return bitmapList
}

export function buildLayers(now: number): Layer[] {
  const { manifest, atlases } = weatherStore.getState()
  if (!manifest) return []
  const { time, cutoff } = clock.getState()
  const ui = useUi.getState()
  const { west, east, south, north, step } = manifest.bounds
  const gridSize: [number, number] = [manifest.tile.width, manifest.tile.height]
  const layers: Layer[] = []

  const rain = ui.rain ? rainField(manifest, time, cutoff, ui.rainSource) : null
  const rainA = rain && atlases.get(rain.a.file)
  const rainB = rain && atlases.get(rain.b.file)
  if (rain && rainA && rainB) {
    layers.push(
      new RainLayer({
        id: 'rain',
        bounds: [west - step / 2, south - step / 2, east + step / 2, north + step / 2],
        imageA: rainA.bitmap,
        imageB: rainB.bitmap,
        tileA: tileRect(rain.a),
        tileB: tileRect(rain.b),
        mixT: rain.t,
        channel: rain.channel,
        gridSize,
        opacity: 0.85,
      }),
    )
  }

  const wind = ui.wind ? windField(manifest, time, cutoff) : null
  const windA = wind && atlases.get(wind.a.file)
  const windB = wind && atlases.get(wind.b.file)
  if (wind && windA && windB) {
    layers.push(
      new WindParticleLayer({
        id: 'wind',
        imageA: windA.bitmap,
        imageB: windB.bitmap,
        tileA: tileRect(wind.a),
        tileB: tileRect(wind.b),
        mixT: wind.t,
        grid: [west, north, step, 0] as Vec4,
        gridSize,
        domain: [west, south, east, north] as Vec4,
        numParticles: quality.particles,
        trail: quality.trail,
        width: quality.width,
        pixelsPerMs: 8,
        clockMs: now,
        animate: !quality.reducedMotion,
        preload: bitmaps(atlases),
      }),
    )
  }
  layers.push(...buildAssetLayers())
  return layers
}
