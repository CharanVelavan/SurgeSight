/**
 * Main roads screened as most exposed, high exposure or on watch (/api/roads), as binary path
 * attributes for the map plus per-section facts for the details panel. Loaded once per storm.
 */

import { createStore } from 'zustand/vanilla'
import { ZONE_HEX } from '@/alerts/field'
import { api, type RoadColumns } from '@/lib/api'
import { hexToRgb } from '@/lib/colors'

export const ROAD_CLASSES = ['motorway', 'trunk', 'primary', 'secondary', 'tertiary'] as const
export type RoadClass = (typeof ROAD_CLASSES)[number]
/** Line width in pixels by road class, widest for motorways. */
const CLASS_WIDTH = [4.5, 4, 3.5, 3, 2.5]

export interface RoadData {
  cols: RoadColumns
  count: number
  /** Index of each section's first point in `positions` (in points), as deck.gl's startIndices. */
  startIndices: Uint32Array
  positions: Float32Array
  /** Per point: RGBA by level, and width by road class. */
  colors: Uint8Array
  widths: Float32Array
}

export const roadsStore = createStore<{ data: RoadData | null; missing: boolean }>(() => ({ data: null, missing: false }))

export function buildRoads(cols: RoadColumns): RoadData {
  const points = cols.path.length / 2
  const positions = Float32Array.from(cols.path)
  const startIndices = Uint32Array.from(cols.starts)
  const colors = new Uint8Array(points * 4)
  const widths = new Float32Array(points)
  const rgb = ZONE_HEX.map(hexToRgb)
  for (let i = 0; i < cols.count; i++) {
    const end = i + 1 < cols.count ? cols.starts[i + 1] : points
    const [r, g, b] = rgb[cols.level[i]] ?? rgb[1]
    for (let p = cols.starts[i]; p < end; p++) {
      colors.set([r, g, b, 255], p * 4)
      widths[p] = CLASS_WIDTH[cols.highway[i]] ?? 2.5
    }
  }
  return { cols, count: cols.count, startIndices, positions, colors, widths }
}

/** The points of one section as [lon, lat] pairs. */
export function sectionPath(d: RoadData, i: number): [number, number][] {
  const end = i + 1 < d.count ? d.startIndices[i + 1] : d.positions.length / 2
  const out: [number, number][] = []
  for (let p = d.startIndices[i]; p < end; p++) out.push([d.positions[p * 2], d.positions[p * 2 + 1]])
  return out
}

export function sectionCentre(d: RoadData, i: number): { lon: number; lat: number } {
  const path = sectionPath(d, i)
  const [lon, lat] = path[Math.floor(path.length / 2)]
  return { lon, lat }
}

export const roadName = (d: RoadData, i: number): string | null => (d.cols.name[i] >= 0 ? d.cols.names[d.cols.name[i]] : null)

let started = false
export async function loadRoads(): Promise<void> {
  if (started) return
  started = true
  try {
    roadsStore.setState({ data: buildRoads(await api.roads()), missing: false })
  } catch (error) {
    // no road layer for this storm (404) or offline without a saved copy: the map simply has no roads
    console.error('[roads] could not load road layer', error)
    roadsStore.setState({ missing: true })
    started = false
  }
}
