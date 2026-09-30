/**
 * Resolve which atlas tiles feed the shaders at a valid time: two neighbouring frames and a mix factor.
 * Past (<= cutoff) comes from analysis wind and IMERG; future comes from the cycle issued at the cutoff,
 * or from IMERG when the observed (validation) source is chosen for rain.
 */

import { HOUR, cycleForCutoff, framesUpTo, toMs, type AtlasEntry, type Manifest } from './manifest'

export type RainSource = 'forecast' | 'observed'

export interface FrameRef {
  file: string
  /** Tile index in the atlas. */
  index: number
  cols: number
  rows: number
}

export interface FieldPair {
  a: FrameRef
  b: FrameRef
  /** 0 → a, 1 → b */
  t: number
  /** Which texture channel holds rain: 0 = R (IMERG), 2 = B (GFS forecast). Unused for wind. */
  channel: 0 | 2
  kind: 'analysis' | 'forecast' | 'observed' | 'validation'
  /** Issue time of the forecast cycle in use, if any. */
  cycle?: string
}

const ref = (e: AtlasEntry, index: number): FrameRef => ({ file: e.file, index, cols: e.cols, rows: e.rows })

/** Interpolate along a regular series of frames starting at `startMs` every `stepMs`, limited to `count` frames. */
function pairIn(e: AtlasEntry, startMs: number, stepMs: number, count: number, timeMs: number) {
  if (count <= 0) return null
  const x = (timeMs - startMs) / stepMs
  if (x < 0 || x > count - 1) return null
  const i = Math.min(Math.floor(x), count - 1)
  const j = Math.min(i + 1, count - 1)
  return { a: ref(e, i), b: ref(e, j), t: j === i ? 0 : x - i }
}

export function windField(m: Manifest, timeMs: number, cutoffMs: number): FieldPair | null {
  const aw = m.analysis_wind
  if (timeMs <= cutoffMs) {
    const p = pairIn(aw, toMs(aw.frames[0]), HOUR, framesUpTo(aw, cutoffMs), timeMs)
    return p && { ...p, channel: 0, kind: 'analysis' }
  }
  const cycle = cycleForCutoff(m, cutoffMs)
  if (!cycle) return null
  const p = pairIn(cycle, toMs(cycle.cycle), cycle.step_hours * HOUR, cycle.frames.length, timeMs)
  return p && { ...p, channel: 0, kind: 'forecast', cycle: cycle.cycle }
}

export function rainField(m: Manifest, timeMs: number, cutoffMs: number, source: RainSource): FieldPair | null {
  const ir = m.observed_rain
  const irStart = toMs(ir.frames[0])
  if (timeMs <= cutoffMs) {
    const p = pairIn(ir, irStart, HOUR, framesUpTo(ir, cutoffMs), timeMs)
    return p && { ...p, channel: 0, kind: 'observed' }
  }
  if (source === 'observed') {
    const p = pairIn(ir, irStart, HOUR, ir.frames.length, timeMs)
    return p && { ...p, channel: 0, kind: 'validation' }
  }
  const cycle = cycleForCutoff(m, cutoffMs)
  if (!cycle) return null
  // f000 carries no accumulated rain, so the first forecast interval starts at the first 3 h step.
  const p = pairIn(cycle, toMs(cycle.cycle), cycle.step_hours * HOUR, cycle.frames.length, timeMs)
  if (!p) return null
  if (p.a.index === 0) return { a: p.b, b: p.b, t: 0, channel: 2, kind: 'forecast', cycle: cycle.cycle }
  return { ...p, channel: 2, kind: 'forecast', cycle: cycle.cycle }
}

/** Texture-space rectangle of a tile: [u0, v0, du, dv]. */
export function tileRect(f: FrameRef): [number, number, number, number] {
  const c = f.index % f.cols
  const r = Math.floor(f.index / f.cols)
  return [c / f.cols, r / f.rows, 1 / f.cols, 1 / f.rows]
}
