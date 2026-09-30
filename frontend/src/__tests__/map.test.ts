import { describe, expect, it } from 'vitest'
import { groupAssets } from '@/data/assets'
import { trackAt, imdClass } from '@/lib/imd'
import { INDIA, IMPACT, fitCamera } from '@/map/view'
import type { TrackPoint } from '@/lib/api'

const cols = {
  count: 4, run_id: null,
  lon: [80.1, 80.2, 80.3, 80.4], lat: [13.1, 13.2, 13.3, 13.4],
  name: ['A', 'B', 'C', 'D'], osm_element: ['node', 'way', 'node', 'node'], osm_id: [1, 2, 3, 4],
  asset_type: ['hospital', 'substation', 'hospital', 'unknown_type'],
  risk_class: ['CRITICAL', 'HIGH', 'MODERATE', 'HIGH'],
  risk_score: [0.9, 0.7, 0.5, 0.6], triage_tier: [1, 2, 3, 2], dominant_hazard: ['wind', 'rain_flood', 'wind', 'wind'],
}

describe('asset grouping', () => {
  const data = groupAssets(cols)
  it('groups known types into typed arrays and keeps the source index', () => {
    expect([...data.groups.keys()].sort()).toEqual(['hospital', 'substation'])
    const h = data.groups.get('hospital')!
    expect(h.count).toBe(2)
    expect([...h.indices]).toEqual([0, 2])
    expect([...h.positions]).toEqual([expect.closeTo(80.1, 4), expect.closeTo(13.1, 4), expect.closeTo(80.3, 4), expect.closeTo(13.3, 4)])
  })
  it('colours each marker by its risk class', () => {
    const h = data.groups.get('hospital')!
    expect([...h.colors.slice(0, 4)]).toEqual([0xb8, 0x32, 0x2a, 235]) // CRITICAL #B8322A
    expect([...h.colors.slice(4, 8)]).toEqual([0xe0, 0xb3, 0x4a, 235]) // MODERATE #E0B34A
  })
})

describe('camera fitting', () => {
  it('shows the whole box: wider viewports are height-limited, narrower ones width-limited', () => {
    const wide = fitCamera(INDIA, 3000, 700)
    const narrow = fitCamera(INDIA, 700, 3000)
    expect(wide.zoom).toBeGreaterThan(narrow.zoom - 3)
    expect(fitCamera(INDIA, 1440, 860).zoom).toBeCloseTo(4.7, 1)
  })
  it('centres on the box', () => {
    const c = fitCamera(IMPACT, 1000, 800).center
    expect(c.lng).toBeCloseTo((IMPACT.west + IMPACT.east) / 2, 6)
    expect(c.lat).toBeGreaterThan(IMPACT.south)
    expect(c.lat).toBeLessThan(IMPACT.north)
  })
  it('zooms further into the smaller impact box', () => {
    expect(fitCamera(IMPACT, 1440, 860).zoom).toBeGreaterThan(fitCamera(INDIA, 1440, 860).zoom + 2)
  })
})

describe('track', () => {
  const track: TrackPoint[] = [
    { time: '2023-12-01T00:00:00Z', lat: 10, lon: 85, wind_kt: 30, pressure_hpa: 1000 },
    { time: '2023-12-01T06:00:00Z', lat: 12, lon: 83, wind_kt: 40, pressure_hpa: 996 },
  ]
  it('interpolates linearly and is null outside the track', () => {
    const mid = trackAt(track, Date.parse('2023-12-01T03:00:00Z'))!
    expect([mid.lat, mid.lon, mid.wind_kt]).toEqual([11, 84, 35])
    expect(trackAt(track, Date.parse('2023-11-30T00:00:00Z'))).toBeNull()
    expect(trackAt(track, Date.parse('2023-12-02T00:00:00Z'))).toBeNull()
  })
  it('classifies at the IMD thresholds', () => {
    expect(imdClass(64).short).toBe('VSCS')
    expect(imdClass(63.9).short).toBe('SCS')
  })
})
