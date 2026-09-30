/**
 * Adaptive quality (docs/UI_PLAN.md §4.6): particle budget by device class, stepped down when the measured
 * frame time stays over budget for two seconds. `?particles=N` pins the count for measurements.
 */

import { usePrefs } from '@/app/prefs'

const params = new URLSearchParams(location.search)
const pinned = Number(params.get('particles')) || 0

function initialBudget(): number {
  if (pinned) return pinned
  // Spawned only inside the visible part of the domain, so density stays constant as the map zooms.
  // Kept light on purpose: the wind is context for the storm, not the subject of the screen.
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || usePrefs.getState().lite) return 5000
  const w = Math.min(screen.width, innerWidth)
  if (w < 640) return 5000
  if (w < 1100) return 9000
  return 14000
}

export const quality = {
  particles: initialBudget(),
  trail: innerWidth < 640 ? 14 : 20,
  width: innerWidth < 640 ? 0.7 : 0.5,
  reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches || usePrefs.getState().lite,
}

/** Rolling frame stats; also read by the ?perf=1 overlay and by the fps check in tests. */
export const perf = {
  fps: 0,
  frameMs: 0,
  samples: [] as number[],
}

let slowSince = 0
const MIN_PARTICLES = 4000

export function recordFrame(now: number, dt: number): void {
  perf.samples.push(dt)
  if (perf.samples.length > 120) perf.samples.shift()
  const avg = perf.samples.reduce((a, b) => a + b, 0) / perf.samples.length
  perf.frameMs = avg
  perf.fps = 1000 / avg
  if (pinned || perf.samples.length < 60) return
  // Budget: 55 fps. Hidden tabs report huge dt; the clock clamps them, so they read as slow but pause first.
  if (avg > 1000 / 55) {
    if (!slowSince) slowSince = now
    if (now - slowSince > 2000 && quality.particles > MIN_PARTICLES) {
      quality.particles = Math.max(MIN_PARTICLES, Math.round(quality.particles * 0.7))
      slowSince = 0
      perf.samples.length = 0
    }
  } else {
    slowSince = 0
  }
}

;(window as unknown as { __surgesight: unknown }).__surgesight = { perf, quality }
