import { describe, expect, it } from 'vitest'
import { HOUR, cycleForCutoff, type Manifest } from '@/weather/manifest'
import { rainField, tileRect, windField } from '@/weather/field'
import { decodeRain, decodeWind } from '@/weather/atlas'

const iso = (ms: number) => new Date(ms).toISOString().replace('.000', '')
const START = Date.UTC(2023, 10, 30)
const hours = (n: number, from = START, step = HOUR) => Array.from({ length: n }, (_, i) => iso(from + i * step))

/** Same shape as data/processed/weather/manifest.json: 169 hourly frames, 15 cycles × 25 steps. */
const manifest: Manifest = {
  bounds: { west: 72, east: 100, south: 0, north: 25, step: 0.25 },
  tile: { width: 113, height: 101 },
  encoding: { wind: { min: -40, max: 40 }, rain: { max: 200 } },
  window: { start: iso(START), end: iso(START + 168 * HOUR) },
  analysis_wind: { file: 'analysis_wind.png', cols: 13, rows: 13, frames: hours(169), source: '' },
  observed_rain: { file: 'observed_rain.png', cols: 13, rows: 13, frames: hours(169), source: '' },
  forecast: Array.from({ length: 15 }, (_, i) => {
    const cycle = START + i * 12 * HOUR
    return { cycle: iso(cycle), file: `forecast_${i}.png`, cols: 5, rows: 5, step_hours: 3, frames: hours(25, cycle, 3 * HOUR), source: '' }
  }),
}

const CUTOFF = Date.UTC(2023, 11, 3, 12)

describe('leakage rule', () => {
  it('uses the latest cycle issued at or before the cutoff', () => {
    expect(cycleForCutoff(manifest, CUTOFF)?.cycle).toBe('2023-12-03T12:00:00Z')
    expect(cycleForCutoff(manifest, CUTOFF - 60_000)?.cycle).toBe('2023-12-03T00:00:00Z')
    expect(cycleForCutoff(manifest, START - HOUR)).toBeNull()
  })

  it('never serves analysis wind or observed rain after the cutoff', () => {
    const w = windField(manifest, CUTOFF + HOUR, CUTOFF)!
    expect(w.kind).toBe('forecast')
    expect(w.a.file).toBe('forecast_7.png')
    const r = rainField(manifest, CUTOFF + HOUR, CUTOFF, 'forecast')!
    expect(r.kind).toBe('forecast')
    expect(r.channel).toBe(2)
  })

  it('labels observed rain after the cutoff as validation', () => {
    const r = rainField(manifest, CUTOFF + 5 * HOUR, CUTOFF, 'observed')!
    expect(r.kind).toBe('validation')
    expect(r.a.file).toBe('observed_rain.png')
  })

  it('shows nothing beyond the +72 h of the cycle', () => {
    expect(windField(manifest, CUTOFF + 73 * HOUR, CUTOFF)).toBeNull()
  })
})

describe('frame interpolation', () => {
  it('mixes neighbouring hourly frames in the past', () => {
    const w = windField(manifest, START + 10.25 * HOUR, CUTOFF)!
    expect([w.a.index, w.b.index, w.t]).toEqual([10, 11, 0.25])
    expect(w.kind).toBe('analysis')
  })

  it('mixes 3-hourly forecast steps and skips the empty f000 rain', () => {
    const w = windField(manifest, CUTOFF + 4.5 * HOUR, CUTOFF)!
    expect([w.a.index, w.b.index, w.t]).toEqual([1, 2, 0.5])
    const r = rainField(manifest, CUTOFF + HOUR, CUTOFF, 'forecast')!
    expect([r.a.index, r.b.index]).toEqual([1, 1])
  })

  it('maps tiles to texture rectangles row-major', () => {
    expect(tileRect({ file: '', index: 14, cols: 13, rows: 13 })).toEqual([1 / 13, 1 / 13, 1 / 13, 1 / 13])
  })
})

describe('byte decoding matches services/weather_frames.py', () => {
  it('decodes wind over ±40 m/s and rain on log1p to 200 mm/h', () => {
    expect(decodeWind(0)).toBe(-40)
    expect(decodeWind(255)).toBe(40)
    expect(decodeRain(0)).toBe(0)
    expect(decodeRain(255)).toBeCloseTo(200, 6)
  })
})
