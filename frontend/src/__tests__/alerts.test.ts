import { describe, expect, it } from 'vitest'
import thresholds from '@config/alert_thresholds.json'
import { alertLevel, hollandKmh, rmwKm, severity, stormWindKmh, WIND_CUTS } from '@/alerts/zones'
import { stormAt } from '@/alerts/storm'
import type { TrackPoint } from '@/lib/api'

describe('alert levels', () => {
  it('agree with the shared table that the Python test also reads', () => {
    for (const [wind, rain, expected] of thresholds.test_table) expect(alertLevel(wind, rain), `${wind} km/h, ${rain} mm/h`).toBe(expected)
  })

  it('severity floors to the level', () => {
    for (const [wind, rain] of thresholds.test_table) {
      expect(Math.min(3, Math.floor(Math.max(severity(wind, WIND_CUTS), severity(rain, thresholds.rain_mm_h))))).toBe(alertLevel(wind, rain))
    }
  })
})

describe('storm wind', () => {
  it('matches the Python Holland profile', () => {
    // services.hazards.wind_field: holland_kmh(50, 100, 30) and rmw_km(25, 13)
    expect(hollandKmh(50, 100, 30)).toBeCloseTo(89.09221593271272, 6)
    expect(rmwKm(25, 13)).toBeCloseTo(39.2322635974947, 6)
  })

  it('is strongest at the radius of maximum wind and stronger right of the track', () => {
    const s = { lat: 13, lon: 80, vmaxKmh: 120, speedKmh: 20, headingDeg: 0 }
    const rmw = rmwKm(120 / 3.6, 13)
    const east = stormWindKmh(s, 13, 80 + rmw / 108.4)
    const west = stormWindKmh(s, 13, 80 - rmw / 108.4)
    expect(east).toBeGreaterThan(west)
    expect(stormWindKmh(s, 13, 85)).toBeLessThan(east)
  })
})

describe('storm position without hindsight', () => {
  const track: TrackPoint[] = [0, 6, 12, 18].map(h => ({ time: new Date(Date.UTC(2023, 11, 3, h)).toISOString(), lat: 12 + h / 6, lon: 83 - h / 6, wind_kt: 60 + h, pressure_hpa: 980 }))
  const forecast = {
    models: { wind_informed_kalman: { label: '', forecast: [{ lead_hours: 6, timestamp: '2023-12-03T18:00:00Z', lat: 20, lon: 70, uncertainty_radius_km: 50 }, { lead_hours: 12, timestamp: '2023-12-04T00:00:00Z', lat: 21, lon: 69, uncertainty_radius_km: 60 }] } },
  } as never
  it('uses the observed track up to the cutoff and the forecast after it', () => {
    const cutoff = Date.UTC(2023, 11, 3, 12)
    const before = stormAt(track, forecast, Date.UTC(2023, 11, 3, 6), cutoff)!
    expect(before.lat).toBeCloseTo(13, 5)
    const after = stormAt(track, forecast, Date.UTC(2023, 11, 3, 21), cutoff)!
    expect(after.lat).toBeGreaterThan(20)
    expect(after.vmaxKmh).toBeCloseTo(72 * 1.852, 3)
    expect(stormAt(track, null, Date.UTC(2023, 11, 3, 21), cutoff)).toBeNull()
  })
})
