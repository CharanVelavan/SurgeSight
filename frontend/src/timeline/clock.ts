/**
 * The frame clock. It owns playback time outside React: one requestAnimationFrame loop advances it and
 * notifies frame listeners (the map), while React reads it through a throttled hook (≈10 Hz).
 */

import { useEffect, useState } from 'react'
import { createStore } from 'zustand/vanilla'
import { HOUR } from '@/weather/manifest'

export const SPEEDS = [1, 2, 4, 8] as const
/** Valid-time hours advanced per wall-clock second at 1×. */
export const HOURS_PER_SECOND = 1

export interface ClockState {
  start: number
  end: number
  /** Valid time being shown (ms UTC). */
  time: number
  /** Bulletin cutoff: observed past on the left, forecast future on the right (ms UTC). */
  cutoff: number
  playing: boolean
  speed: (typeof SPEEDS)[number]
}

export const clock = createStore<ClockState>(() => ({
  start: Date.UTC(2023, 10, 30),
  end: Date.UTC(2023, 11, 7),
  time: Date.UTC(2023, 11, 3, 12),
  cutoff: Date.UTC(2023, 11, 3, 12),
  playing: false,
  speed: 1,
}))

export const clamp = (x: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, x))

/** Advance playback by `dtMs` of wall time; stops at the end of the window. Pure, for tests. */
export function advance(s: ClockState, dtMs: number): Partial<ClockState> {
  if (!s.playing) return {}
  const time = s.time + (dtMs / 1000) * HOURS_PER_SECOND * s.speed * HOUR
  return time >= s.end ? { time: s.end, playing: false } : { time }
}

export const clockActions = {
  setTime: (t: number) => clock.setState(s => ({ time: clamp(t, s.start, s.end) })),
  step: (hours: number) =>
    clock.setState(s => ({ time: clamp(Math.round((s.time + hours * HOUR) / HOUR) * HOUR, s.start, s.end) })),
  setCutoff: (t: number) => clock.setState(s => ({ cutoff: clamp(t, s.start, s.end) })),
  toggle: () =>
    clock.setState(s => ({ playing: !s.playing, time: !s.playing && s.time >= s.end ? s.start : s.time })),
  setSpeed: (speed: ClockState['speed']) => clock.setState({ speed }),
  setWindow: (start: number, end: number) => clock.setState(s => ({ start, end, time: clamp(s.time, start, end) })),
}

type FrameListener = (now: number, dt: number) => void
const listeners = new Set<FrameListener>()
let raf = 0
let last = 0

function tick(now: number) {
  const dt = last ? Math.min(now - last, 100) : 16.7
  last = now
  const patch = advance(clock.getState(), dt)
  if (Object.keys(patch).length) clock.setState(patch)
  for (const l of listeners) l(now, dt)
  raf = requestAnimationFrame(tick)
}

/** Subscribe to every animation frame. The loop runs while at least one listener is attached. */
export function onFrame(listener: FrameListener): () => void {
  listeners.add(listener)
  if (!raf) {
    last = 0
    raf = requestAnimationFrame(tick)
  }
  return () => {
    listeners.delete(listener)
    if (!listeners.size && raf) {
      cancelAnimationFrame(raf)
      raf = 0
    }
  }
}

/** React view of the clock, re-rendering at most every `intervalMs` while time moves. */
export function useClock<T>(select: (s: ClockState) => T, intervalMs = 100): T {
  const [value, setValue] = useState(() => select(clock.getState()))
  useEffect(() => {
    let pending = false
    let timer = 0
    const unsub = clock.subscribe(s => {
      if (pending) return
      pending = true
      timer = window.setTimeout(() => {
        pending = false
        setValue(() => select(clock.getState()))
      }, s.playing ? intervalMs : 0)
    })
    return () => {
      unsub()
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs])
  return value
}
