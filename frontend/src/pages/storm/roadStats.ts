import { navigate, pathFor } from '@/app/router'
import { sectionCentre, type RoadData } from '@/data/roads'
import type { RoadSummary } from '@/lib/api'
import { useUi } from '@/state/ui'

export interface RoadRow {
  /** Index into the road name table, or -1 for unnamed roads. */
  name: number
  worst: number
  /** Km at level 2 or above. */
  km: number
  highway: number
  /** The section to show on the map: the worst one, longest first. */
  section: number
  districts: string[]
}

/** Named roads with at least one section at level 2 or above, worst first, then the bigger road, then the longer stretch. */
export function worstRoads(d: RoadData): RoadRow[] {
  const byName = new Map<number, RoadRow>()
  const c = d.cols
  for (let i = 0; i < d.count; i++) {
    if (c.level[i] < 2 || c.name[i] < 0) continue
    let r = byName.get(c.name[i])
    if (!r) {
      r = { name: c.name[i], worst: 0, km: 0, highway: c.highway[i], section: i, districts: [] }
      byName.set(c.name[i], r)
    }
    r.km += c.km[i]
    r.highway = Math.min(r.highway, c.highway[i])
    if (c.level[i] > r.worst || (c.level[i] === r.worst && c.km[i] > c.km[r.section])) {
      r.worst = c.level[i]
      r.section = i
    }
    const dist = c.district[i]
    if (dist && !r.districts.includes(dist)) r.districts.push(dist)
  }
  return [...byName.values()].sort((a, b) => b.worst - a.worst || a.highway - b.highway || b.km - a.km)
}

/** How much more often the most-exposed sections showed water than open ones in the Sentinel-2 proxy. */
export function observedRatio(s: RoadSummary): { high: string; open: string; km: string } | null {
  const v = s.validation
  const high = v.by_flood_level.most_exposed?.observed_flooded_share
  const open = v.by_flood_level.open?.observed_flooded_share
  if (high == null || open == null || !v.sections_observed) return null
  return { high: String(Math.round(high * 100)), open: String(Math.round(open * 100)), km: String(Math.round(v.km_observed)) }
}

/** Open the storm's map zoomed to one road section, with its details shown. */
export function showRoadOnMap(stormId: string, d: RoadData, index: number): void {
  const { lon, lat } = sectionCentre(d, index)
  useUi.getState().set({ view: 'impact', roads: true, selectedRoad: index, selectedAsset: null })
  navigate(pathFor({ name: 'storm', id: stormId, tab: 'map' }))
  setTimeout(() => useUi.getState().set({ focus: { lon, lat, zoom: 12.5 } }), 60)
}
