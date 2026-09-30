/**
 * Loads every atlas PNG once. Each atlas keeps an ImageBitmap (uploaded to the GPU by the layers) and a
 * CPU copy of the bytes for the cursor readout. Bitmaps are decoded without colour conversion so the
 * encoded bytes survive exactly.
 */

import { createStore } from 'zustand/vanilla'
import { WIND_MAX, RAIN_MAX, atlasFiles, type Manifest } from './manifest'
import type { FieldPair, FrameRef } from './field'

export interface Atlas {
  file: string
  bitmap: ImageBitmap
  pixels: Uint8ClampedArray
  width: number
  height: number
}

interface WeatherState {
  manifest: Manifest | null
  atlases: Map<string, Atlas>
  loaded: number
  total: number
  error: string | null
}

export const weatherStore = createStore<WeatherState>(() => ({
  manifest: null,
  atlases: new Map(),
  loaded: 0,
  total: 0,
  error: null,
}))

async function loadAtlas(file: string, version?: string): Promise<Atlas> {
  const res = await fetch(`/api/weather/${file}${version ? `?v=${version}` : ''}`)
  if (!res.ok) throw new Error(`${file}: HTTP ${res.status}`)
  const bitmap = await createImageBitmap(await res.blob(), { premultiplyAlpha: 'none', colorSpaceConversion: 'none' })
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height)
  const ctx = canvas.getContext('2d', { willReadFrequently: true })!
  ctx.drawImage(bitmap, 0, 0)
  const pixels = ctx.getImageData(0, 0, bitmap.width, bitmap.height).data
  return { file, bitmap, pixels, width: bitmap.width, height: bitmap.height }
}

let started = false

export async function loadWeather(): Promise<void> {
  if (started) return
  started = true
  try {
    const res = await fetch('/api/weather/manifest', { cache: 'no-cache' })
    if (!res.ok) throw new Error(`manifest: HTTP ${res.status}`)
    const manifest = (await res.json()) as Manifest
    const files = atlasFiles(manifest)
    weatherStore.setState({ manifest, total: files.length })
    // Hourly past fields first, so the opening frame appears as early as possible.
    await Promise.all(
      files.map(async file => {
        const atlas = await loadAtlas(file, manifest.version)
        const atlases = new Map(weatherStore.getState().atlases).set(file, atlas)
        weatherStore.setState(s => ({ atlases, loaded: s.loaded + 1 }))
      }),
    )
  } catch (err) {
    weatherStore.setState({ error: err instanceof Error ? err.message : String(err) })
  }
}

// --- CPU sampling for the cursor readout -------------------------------------------------------------

export const decodeWind = (byte: number) => (byte / 255) * 2 * WIND_MAX - WIND_MAX
export const decodeRain = (byte: number) => Math.expm1((byte / 255) * Math.log1p(RAIN_MAX))

/** Bilinear sample of one channel of a tile at a lon/lat, in raw byte units (fractional). */
function sampleTile(atlas: Atlas, f: FrameRef, m: Manifest, lon: number, lat: number, channel: number): number | null {
  const { west, north, step } = m.bounds
  const { width: W, height: H } = m.tile
  const x = (lon - west) / step
  const y = (north - lat) / step
  if (x < 0 || y < 0 || x > W - 1 || y > H - 1) return null
  const x0 = Math.floor(x), y0 = Math.floor(y)
  const x1 = Math.min(x0 + 1, W - 1), y1 = Math.min(y0 + 1, H - 1)
  const fx = x - x0, fy = y - y0
  const ox = (f.index % f.cols) * W
  const oy = Math.floor(f.index / f.cols) * H
  const at = (px: number, py: number) => atlas.pixels[((oy + py) * atlas.width + ox + px) * 4 + channel]
  const top = at(x0, y0) * (1 - fx) + at(x1, y0) * fx
  const bottom = at(x0, y1) * (1 - fx) + at(x1, y1) * fx
  return top * (1 - fy) + bottom * fy
}

/** Samples both frames, decodes each, then mixes, which is what the shaders do. */
function samplePair(p: FieldPair, m: Manifest, lon: number, lat: number, channel: number, decode: (b: number) => number): number | null {
  const { atlases } = weatherStore.getState()
  const A = atlases.get(p.a.file), B = atlases.get(p.b.file)
  if (!A || !B) return null
  const a = sampleTile(A, p.a, m, lon, lat, channel)
  const b = sampleTile(B, p.b, m, lon, lat, channel)
  return a === null || b === null ? null : decode(a) * (1 - p.t) + decode(b) * p.t
}

export function sampleWind(p: FieldPair, m: Manifest, lon: number, lat: number): { u: number; v: number } | null {
  const u = samplePair(p, m, lon, lat, 0, decodeWind)
  const v = samplePair(p, m, lon, lat, 1, decodeWind)
  return u === null || v === null ? null : { u, v }
}

export function sampleRain(p: FieldPair, m: Manifest, lon: number, lat: number): number | null {
  return samplePair(p, m, lon, lat, p.channel, decodeRain)
}
