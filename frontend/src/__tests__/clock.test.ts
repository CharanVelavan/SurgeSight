import { describe, expect, it } from 'vitest'
import { HOUR } from '@/weather/manifest'
import { advance, type ClockState } from '@/timeline/clock'
import { imdClass } from '@/lib/imd'
import { formatIST, windFrom } from '@/lib/format'

const base: ClockState = { start: 0, end: 100 * HOUR, time: 10 * HOUR, cutoff: 50 * HOUR, playing: true, speed: 2 }

describe('clock', () => {
  it('advances valid time by speed × hours per second', () => {
    expect(advance(base, 1000)).toEqual({ time: 12 * HOUR })
  })
  it('stops at the end of the window', () => {
    expect(advance({ ...base, time: 99.5 * HOUR }, 1000)).toEqual({ time: 100 * HOUR, playing: false })
  })
  it('does nothing while paused', () => {
    expect(advance({ ...base, playing: false }, 1000)).toEqual({})
  })
})

describe('formatting', () => {
  it('shows IST', () => {
    expect(formatIST(Date.UTC(2023, 11, 3, 12))).toBe('03 Dec 17:30 IST')
  })
  it('gives the direction the wind blows from', () => {
    expect(windFrom(0, -10)).toBe('N')
    expect(windFrom(-10, 0)).toBe('E')
  })
  it('classifies by IMD thresholds', () => {
    expect(imdClass(55).short).toBe('SCS')
    expect(imdClass(30).short).toBe('DD')
  })
})
