import { describe, expect, it } from 'vitest'
import { buildRoads, type RoadData } from '@/data/roads'
import type { RoadColumns } from '@/lib/api'
import { worstRoads } from '@/pages/storm/roadStats'

const cols: RoadColumns = {
  model_version: 'test', count: 3, names: ['Beach Road', 'Grand Trunk Road'],
  path: [80, 13, 80.01, 13, 80.01, 13, 80.02, 13, 80.02, 13, 80.03, 13], starts: [0, 2, 4],
  id: ['1:0', '1:1', '2:0'], name: [0, 0, 1], highway: [2, 2, 0], level: [2, 3, 2],
  cause: ['flood', 'wind', 'surge'], km: [1.2, 0.8, 1.5], rain_mm: [150, 150, 0], wind_kmh: [50, 120, 70],
  surge_m: [0, 0, 1], elevation_min_m: [3, 5, 2], hand_min_m: [1, 2, 1], district: ['A', 'A', 'B'],
}

describe('buildRoads', () => {
  it('builds typed path attributes and section boundaries', () => {
    const roads = buildRoads(cols)
    expect(roads.count).toBe(3)
    expect([...roads.startIndices]).toEqual([0, 2, 4])
    expect([...roads.positions]).toHaveLength(12)
    expect([...roads.widths.slice(0, 2)]).toEqual([3.5, 3.5])
    expect([...roads.colors.slice(0, 4)]).toEqual([...roads.colors.slice(4, 8)])
  })
})

describe('worstRoads', () => {
  it('groups names, totals affected km and sorts by severity', () => {
    const rows = worstRoads(buildRoads(cols) as RoadData)
    expect(rows.map(r => cols.names[r.name])).toEqual(['Beach Road', 'Grand Trunk Road'])
    expect(rows[0]).toMatchObject({ worst: 3, km: 2, section: 1 })
    expect(rows[1]).toMatchObject({ worst: 2, km: 1.5, highway: 0, section: 2 })
  })
})
