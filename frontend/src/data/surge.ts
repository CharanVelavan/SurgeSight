/** Storm-surge screening estimate at coastal facilities (/api/layers/surge), as typed arrays for the map. */

import { createStore } from 'zustand/vanilla'
import { hexToRgb } from '@/lib/colors'

export const SURGE_STOPS: readonly [number, string][] = [
  [0, '#9AD9EC'],
  [0.25, '#3B9AD9'],
  [0.5, '#3A5FCD'],
  [0.75, '#6A3FB8'],
  [1, '#9B2F9E'],
]

function surgeColor(m: number): [number, number, number, number] {
  const x = Math.min(1, Math.max(0, m))
  let i = 1
  while (i < SURGE_STOPS.length - 1 && x > SURGE_STOPS[i][0]) i++
  const [a, ca] = SURGE_STOPS[i - 1], [b, cb] = SURGE_STOPS[i]
  const f = (x - a) / (b - a)
  const p = hexToRgb(ca), q = hexToRgb(cb)
  return [0, 1, 2].map(k => Math.round(p[k] + (q[k] - p[k]) * f)).concat(170) as [number, number, number, number]
}

export interface SurgeData {
  count: number
  positions: Float32Array
  colors: Uint8Array
  metres: Float32Array
}

export const surgeStore = createStore<{ data: SurgeData | null }>(() => ({ data: null }))

let started = false
export async function loadSurge(): Promise<void> {
  if (started) return
  started = true
  try {
    const res = await fetch('/api/layers/surge')
    if (!res.ok) throw new Error(String(res.status))
    const fc = (await res.json()) as { features: { geometry: { coordinates: [number, number] }; properties: { surge_m: number } }[] }
    const n = fc.features.length
    const positions = new Float32Array(n * 2), colors = new Uint8Array(n * 4), metres = new Float32Array(n)
    fc.features.forEach((f, i) => {
      positions.set(f.geometry.coordinates, i * 2)
      metres[i] = f.properties.surge_m
      colors.set(surgeColor(f.properties.surge_m), i * 4)
    })
    surgeStore.setState({ data: { count: n, positions, colors, metres } })
  } catch {
    started = false
  }
}
