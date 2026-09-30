/**
 * Weather frame catalogue (built by scripts/build_weather_frames.py) and the leakage rule, mirrored from
 * services/weather_frames.frames_for_cutoff so the client never shows what was not knowable at the cutoff.
 */

export interface Bounds { west: number; east: number; south: number; north: number; step: number }

export interface AtlasEntry {
  file: string
  cols: number
  rows: number
  /** ISO UTC valid times, one per tile in row-major order. */
  frames: string[]
  source: string
}

export interface ForecastEntry extends AtlasEntry {
  cycle: string
  step_hours: number
}

export interface Manifest {
  /** Hash of the atlas files; part of every image URL so rebuilt images are never served from a stale cache. */
  version?: string
  bounds: Bounds
  tile: { width: number; height: number }
  encoding: {
    wind: { min: number; max: number }
    rain: { max: number }
  }
  window: { start: string; end: string }
  analysis_wind: AtlasEntry
  observed_rain: AtlasEntry
  forecast: ForecastEntry[]
}

export const WIND_MAX = 40
export const RAIN_MAX = 200
export const HOUR = 3_600_000

export const toMs = (iso: string) => Date.parse(iso)

/** Latest GFS cycle issued at or before the cutoff, or null before the first cycle. */
export function cycleForCutoff(manifest: Manifest, cutoffMs: number): ForecastEntry | null {
  let best: ForecastEntry | null = null
  for (const c of manifest.forecast) {
    const t = toMs(c.cycle)
    if (t <= cutoffMs && (!best || t > toMs(best.cycle))) best = c
  }
  return best
}

/** Number of leading frames of an hourly atlas that are at or before the cutoff. */
export function framesUpTo(entry: AtlasEntry, cutoffMs: number): number {
  let n = 0
  while (n < entry.frames.length && toMs(entry.frames[n]) <= cutoffMs) n++
  return n
}

export function atlasFiles(manifest: Manifest): string[] {
  return [manifest.analysis_wind.file, manifest.observed_rain.file, ...manifest.forecast.map(c => c.file)]
}
