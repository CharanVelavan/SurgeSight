/**
 * Infrastructure at risk (hospitals, substations, police, ...) from /api/assets?format=columnar.
 * Grouped once into typed arrays per asset type so deck.gl layers take binary attributes and never
 * rebuild while the map animates.
 */

import { createStore } from 'zustand/vanilla'
import { api } from '@/lib/api'
import { RISK, hexToRgb, type RiskClass } from '@/lib/colors'

export const ASSET_TYPES = {
  hospital: { label: 'Hospitals', glyph: 'cross' },
  substation: { label: 'Power substations', glyph: 'bolt' },
  police_station: { label: 'Police stations', glyph: 'shield' },
  fire_station: { label: 'Fire stations', glyph: 'flame' },
  shelter: { label: 'Shelters', glyph: 'house' },
  school: { label: 'Schools', glyph: 'diamond' },
  water_facility: { label: 'Water facilities', glyph: 'drop' },
  fishing_harbour: { label: 'Fishing harbours', glyph: 'hex' },
} as const

export type AssetType = keyof typeof ASSET_TYPES
export const ASSET_ORDER = Object.keys(ASSET_TYPES) as AssetType[]

export interface AssetGroup {
  type: AssetType
  count: number
  /** Index of each member in the full columnar arrays, for hover lookups. */
  indices: Int32Array
  positions: Float32Array
  /** RGBA bytes by risk class. */
  colors: Uint8Array
}

export interface AssetData {
  runId: string | null
  count: number
  name: string[]
  type: string[]
  riskClass: string[]
  riskScore: number[]
  lon: number[]
  lat: number[]
  tier: number[]
  hazard: string[]
  groups: Map<AssetType, AssetGroup>
}

interface AssetsState {
  data: AssetData | null
  error: string | null
}

export const assetsStore = createStore<AssetsState>(() => ({ data: null, error: null }))

const rgba = (cls: string): [number, number, number, number] => {
  const c = RISK[(cls in RISK ? cls : 'LOW') as RiskClass].color
  return [...hexToRgb(c), 235]
}

export function groupAssets(cols: Awaited<ReturnType<typeof api.assets>>): AssetData {
  const buckets = new Map<AssetType, number[]>()
  cols.asset_type.forEach((t, i) => {
    if (!(t in ASSET_TYPES)) return
    const list = buckets.get(t as AssetType) ?? []
    list.push(i)
    buckets.set(t as AssetType, list)
  })
  const groups = new Map<AssetType, AssetGroup>()
  for (const [type, idx] of buckets) {
    const positions = new Float32Array(idx.length * 2)
    const colors = new Uint8Array(idx.length * 4)
    idx.forEach((src, j) => {
      positions[j * 2] = cols.lon[src]
      positions[j * 2 + 1] = cols.lat[src]
      colors.set(rgba(cols.risk_class[src]), j * 4)
    })
    groups.set(type, { type, count: idx.length, indices: Int32Array.from(idx), positions, colors })
  }
  return {
    runId: cols.run_id, count: cols.count, name: cols.name, type: cols.asset_type, riskClass: cols.risk_class,
    riskScore: cols.risk_score, lon: cols.lon, lat: cols.lat, tier: cols.triage_tier, hazard: cols.dominant_hazard, groups,
  }
}

let started = false
export async function loadAssets(): Promise<void> {
  if (started) return
  started = true
  try {
    assetsStore.setState({ data: groupAssets(await api.assets()) })
  } catch (err) {
    assetsStore.setState({ error: err instanceof Error ? err.message : String(err) })
  }
}
