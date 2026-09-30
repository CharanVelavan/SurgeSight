/** Builds the deck.gl layer list for one animation frame from the clock, the weather store and the UI. */

import type { Layer } from '@deck.gl/core'
import { useUi } from '@/state/ui'
import { clock } from '@/timeline/clock'
import { weatherStore } from '@/weather/atlas'
import { extField, rainField, tileRect, windField } from '@/weather/field'
import { RainLayer } from '@/layers/rain/RainLayer'
import { CLOUD_RAMP, CLOUD_RAMP_LIGHT, HUMIDITY_RAMP, TEMP_RAMP } from '@/lib/colors'
import { makeScalarLayer } from '@/layers/scalar/ScalarLayer'
import { WindParticleLayer } from '@/layers/wind/WindParticleLayer'
import { ZoneLayer } from '@/layers/zones/ZoneLayer'
import { stormAt } from '@/alerts/storm'
import { zoneImage } from '@/alerts/store'
import { trackStore } from '@/data/track'
import { PathLayer, ScatterplotLayer } from '@deck.gl/layers'
import { surgeStore, type SurgeData } from '@/data/surge'
import { roadsStore, sectionPath, type RoadData } from '@/data/roads'
import { INFRA_ZOOM, buildAssetLayers } from './assetLayers'
import { buildTrackLayers } from './trackLayers'
import { quality } from './quality'

type Vec4 = [number, number, number, number]

const FIELD_LAYERS = {
  cloud: makeScalarLayer({ name: 'cloud', channel: 0, min: 0, max: 100, ramp: CLOUD_RAMP }),
  cloudLight: makeScalarLayer({ name: 'cloudLight', channel: 0, min: 0, max: 100, ramp: CLOUD_RAMP_LIGHT }),
  temperature: makeScalarLayer({ name: 'temperature', channel: 1, min: -30, max: 50, ramp: TEMP_RAMP }),
  humidity: makeScalarLayer({ name: 'humidity', channel: 2, min: 0, max: 100, ramp: HUMIDITY_RAMP }),
}

let bitmapList: ImageBitmap[] = []
let bitmapSource: unknown = null
function bitmaps(atlases: Map<string, { bitmap: ImageBitmap }>): ImageBitmap[] {
  if (atlases !== bitmapSource) {
    bitmapSource = atlases
    bitmapList = [...atlases.values()].map(a => a.bitmap)
  }
  return bitmapList
}

type SurgeBinary = { length: number; attributes: Record<string, { value: Float32Array | Uint8Array; size: number }> }
const surgeCache = new WeakMap<SurgeData, SurgeBinary>()
function surgeBinary(d: SurgeData) {
  let b = surgeCache.get(d)
  if (!b) {
    b = { length: d.count, attributes: { getPosition: { value: d.positions, size: 2 }, getFillColor: { value: d.colors, size: 4 } } }
    surgeCache.set(d, b)
  }
  return b
}

type RoadBinary = { length: number; startIndices: Uint32Array; attributes: Record<string, { value: Float32Array | Uint8Array; size: number }> }
const roadCache = new WeakMap<RoadData, { main: RoadBinary; casing: RoadBinary }>()
function roadBinary(d: RoadData) {
  let b = roadCache.get(d)
  if (!b) {
    const getPath = { value: d.positions, size: 2 }
    const getWidth = { value: d.widths, size: 1 }
    b = {
      main: { length: d.count, startIndices: d.startIndices, attributes: { getPath, getWidth, getColor: { value: d.colors, size: 4 } } },
      casing: { length: d.count, startIndices: d.startIndices, attributes: { getPath, getWidth } },
    }
    roadCache.set(d, b)
  }
  return b
}
let selectedPath: { data: RoadData; index: number; path: [number, number][][] } | null = null
function selectedRoadPath(d: RoadData, index: number) {
  if (!selectedPath || selectedPath.data !== d || selectedPath.index !== index) selectedPath = { data: d, index, path: [sectionPath(d, index)] }
  return selectedPath.path
}

/** Main roads coloured by level over a thin casing so they read on any basemap; a clicked section is outlined. */
function buildRoadLayers(zoom: number, selected: number | null): Layer[] {
  const d = roadsStore.getState().data
  if (!d) return []
  const b = roadBinary(d)
  const dark = document.documentElement.classList.contains('dark')
  const scale = zoom < 8 ? 0.6 : zoom < 10 ? 0.85 : 1.2
  const common = { _pathType: 'open' as const, widthUnits: 'pixels' as const, widthMinPixels: 1, capRounded: true, jointRounded: true, parameters: { depthCompare: 'always' as const } }
  const layers: Layer[] = [
    new PathLayer({ ...common, id: 'roads-casing', data: b.casing as never, getColor: dark ? [10, 12, 16, 210] : [255, 255, 255, 235], widthScale: scale * 1.9, pickable: false }),
    new PathLayer({
      ...common, id: 'roads', data: b.main as never, widthScale: scale, pickable: true, autoHighlight: true, highlightColor: [255, 255, 255, 110],
      onClick: (info: { index: number }) => {
        if (info.index >= 0) useUi.getState().set({ selectedRoad: info.index, selectedAsset: null })
      },
    }),
  ]
  if (selected !== null && selected < d.count)
    layers.push(
      new PathLayer({
        ...common, id: 'road-selected', data: selectedRoadPath(d, selected), getPath: (p: [number, number][]) => p,
        getColor: dark ? [255, 255, 255, 255] : [20, 24, 30, 255], getWidth: 3, widthScale: 1, widthMinPixels: 3, pickable: false,
      }),
    )
  return layers
}

export function buildLayers(now: number): Layer[] {
  const { manifest, atlases } = weatherStore.getState()
  if (!manifest) return []
  const { time, cutoff } = clock.getState()
  const ui = useUi.getState()
  const { west, east, south, north, step } = manifest.bounds
  const gridSize: [number, number] = [manifest.tile.width, manifest.tile.height]
  const layers: Layer[] = []

  const ext = ui.field !== 'none' ? extField(manifest, time, cutoff) : null
  const extA = ext && atlases.get(ext.a.file)
  const extB = ext && atlases.get(ext.b.file)
  if (ui.field !== 'none' && ext && extA && extB) {
    const dark = document.documentElement.classList.contains('dark')
    const Field = ui.field === 'cloud' && !dark ? FIELD_LAYERS.cloudLight : FIELD_LAYERS[ui.field]
    layers.push(
      new Field({
        id: ui.field,
        bounds: [west - step / 2, south - step / 2, east + step / 2, north + step / 2],
        imageA: extA.bitmap, imageB: extB.bitmap, tileA: tileRect(ext.a), tileB: tileRect(ext.b), mixT: ext.t, gridSize, opacity: 0.9,
      }),
    )
  }

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

  if (ui.zones) {
    const { timeline, forecast } = trackStore.getState()
    const image = zoneImage(manifest, time, cutoff, ui.rainSource, stormAt(timeline?.track, forecast, time, cutoff))
    if (image)
      layers.push(
        new ZoneLayer({
          id: 'alert-zones', image, bounds: [west - step / 2, south - step / 2, east + step / 2, north + step / 2],
          textureParameters: { minFilter: 'linear', magFilter: 'linear' }, pickable: false,
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
        opacity: 0.75,
      }),
    )
  }
  if (ui.mode === 'replay') {
    const surge = surgeStore.getState().data
    if (ui.surge && surge && ui.zoom >= INFRA_ZOOM)
      layers.push(
        new ScatterplotLayer({
          id: 'surge', data: surgeBinary(surge) as never, radiusUnits: 'meters', getRadius: 4000, radiusMinPixels: 9, stroked: false,
          pickable: false, parameters: { depthCompare: 'always' },
        }),
      )
    if (ui.roads && ui.zoom >= INFRA_ZOOM) layers.push(...buildRoadLayers(ui.zoom, ui.selectedRoad))
    layers.push(...(ui.track ? buildTrackLayers() : []), ...buildAssetLayers())
  }
  return layers
}
