/**
 * Timeline with the now-line split (docs/UI_PLAN.md U13): one valid-time scrubber; a draggable cutoff
 * separates the observed past (solid) from the forecast future (dashed, limited to the +72 h of the cycle
 * issued at the cutoff). The playhead moves by direct DOM writes, not React renders.
 */

import { useEffect, useRef } from 'react'
import { Pause, Play } from 'lucide-react'
import { useTimeline } from '@/app/queries'
import { formatCycle, formatDay, formatIST } from '@/lib/format'
import { cn } from '@/lib/utils'
import { HOUR, cycleForCutoff, toMs } from '@/weather/manifest'
import { useWeather } from '@/weather/useWeather'
import { SPEEDS, clock, clockActions, useClock } from './clock'

const CUTOFF_STEP = 12 * HOUR
const IST_OFFSET = 5.5 * HOUR

const pct = (t: number, start: number, end: number) => `${(((t - start) / (end - start)) * 100).toFixed(3)}%`

export function Timeline() {
  const { data: timeline } = useTimeline()
  const manifest = useWeather(s => s.manifest)
  const { start, end, cutoff, playing, speed } = useClock(s => ({ start: s.start, end: s.end, cutoff: s.cutoff, playing: s.playing, speed: s.speed }), 100)
  const time = useClock(s => s.time, 200)
  const barRef = useRef<HTMLDivElement>(null)
  const headRef = useRef<HTMLDivElement>(null)

  // Window follows the weather data.
  useEffect(() => {
    if (manifest) clockActions.setWindow(toMs(manifest.window.start), toMs(manifest.window.end))
  }, [manifest])

  // Playhead: every clock change, straight to the DOM.
  useEffect(() => {
    const place = () => {
      const s = clock.getState()
      if (headRef.current) headRef.current.style.left = pct(s.time, s.start, s.end)
    }
    place()
    return clock.subscribe(place)
  }, [])

  // Keyboard control; ignored while typing in a field.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      if (el.closest('input, textarea, [contenteditable="true"], [role="dialog"]') || e.metaKey || e.ctrlKey || e.altKey) return
      const s = clock.getState()
      switch (e.key) {
        case ' ':
          if (el.closest('button, [role="switch"], [role="radio"]')) return
          clockActions.toggle()
          break
        case 'ArrowLeft':
          clockActions.step(e.shiftKey ? -6 : -1)
          break
        case 'ArrowRight':
          clockActions.step(e.shiftKey ? 6 : 1)
          break
        case '[':
          clockActions.setCutoff(s.cutoff - CUTOFF_STEP)
          break
        case ']':
          clockActions.setCutoff(s.cutoff + CUTOFF_STEP)
          break
        case 'Home':
          clockActions.setTime(s.start)
          break
        case 'End':
          clockActions.setTime(s.end)
          break
        default:
          return
      }
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const timeAt = (clientX: number) => {
    const r = barRef.current!.getBoundingClientRect()
    return start + Math.min(1, Math.max(0, (clientX - r.left) / r.width)) * (end - start)
  }

  const drag = (e: React.PointerEvent, apply: (t: number) => void) => {
    e.preventDefault()
    e.stopPropagation()
    const target = e.currentTarget as HTMLElement
    target.setPointerCapture(e.pointerId)
    apply(timeAt(e.clientX))
    const move = (ev: PointerEvent) => apply(timeAt(ev.clientX))
    const up = () => {
      target.removeEventListener('pointermove', move)
      target.removeEventListener('pointerup', up)
      target.removeEventListener('pointercancel', up)
    }
    target.addEventListener('pointermove', move)
    target.addEventListener('pointerup', up)
    target.addEventListener('pointercancel', up)
  }
  const scrub = (t: number) => clockActions.setTime(Math.round(t / (HOUR / 4)) * (HOUR / 4))
  const moveCutoff = (t: number) => clockActions.setCutoff(Math.round(t / CUTOFF_STEP) * CUTOFF_STEP)

  const cycle = manifest ? cycleForCutoff(manifest, cutoff) : null
  const forecastEnd = cycle ? Math.min(end, toMs(cycle.frames[cycle.frames.length - 1])) : cutoff

  // Day ticks at IST midnight.
  const days: number[] = []
  for (let t = Math.ceil((start + IST_OFFSET) / (24 * HOUR)) * 24 * HOUR - IST_OFFSET; t <= end - 12 * HOUR; t += 24 * HOUR) days.push(t)
  const landfall = timeline?.first_over_land ? toMs(timeline.first_over_land.time) : null

  return (
    <section aria-label="Timeline" className="panel pointer-events-auto absolute inset-x-3 bottom-8 z-20 px-3 pt-2 pb-2.5 select-none">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={clockActions.toggle}
          aria-label={playing ? 'Pause' : 'Play'}
          className="grid size-8 place-items-center rounded-lg bg-secondary text-foreground transition-colors hover:bg-accent"
        >
          {playing ? <Pause className="size-4" /> : <Play className="size-4 translate-x-px" />}
        </button>
        <div className="flex rounded-lg bg-secondary p-0.5" role="radiogroup" aria-label="Playback speed">
          {SPEEDS.map(s => (
            <button
              key={s}
              type="button"
              role="radio"
              aria-checked={speed === s}
              onClick={() => clockActions.setSpeed(s)}
              className={cn('num h-7 rounded-md px-2 text-[11px] text-muted-foreground transition-colors', speed === s && 'bg-accent text-foreground')}
            >
              {s}×
            </button>
          ))}
        </div>
        <div className="num ml-1 text-[13px]">{formatIST(time)}</div>
        <div className="ml-auto flex items-center gap-3 text-[11px] text-muted-foreground max-sm:hidden">
          <span>
            Cutoff <span className="num text-foreground">{formatIST(cutoff)}</span>
          </span>
          <span>{cycle ? `GFS ${formatCycle(toMs(cycle.cycle))}` : 'no forecast issued yet'}</span>
          <span className="max-lg:hidden" title="Space play · ←/→ 1 h (Shift 6 h) · [ / ] move cutoff 12 h">
            Keys: space ← → [ ]
          </span>
        </div>
      </div>

      <div
        ref={barRef}
        role="slider"
        tabIndex={0}
        aria-label="Valid time"
        aria-valuemin={start}
        aria-valuemax={end}
        aria-valuenow={time}
        aria-valuetext={formatIST(time)}
        onPointerDown={e => drag(e, scrub)}
        className="relative mt-2 h-9 cursor-pointer touch-none rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring/60"
      >
        {/* track: observed past (solid), forecast window (dashed), beyond forecast (faint) */}
        <div className="absolute inset-x-0 top-3 h-1.5 rounded-full bg-white/[0.06]" />
        <div className="absolute top-3 h-1.5 rounded-l-full bg-primary/55" style={{ left: 0, width: pct(cutoff, start, end) }} />
        <div
          className="absolute top-3 h-1.5"
          style={{
            left: pct(cutoff, start, end),
            width: `calc(${pct(forecastEnd, start, end)} - ${pct(cutoff, start, end)})`,
            background: 'repeating-linear-gradient(90deg, rgba(127,167,217,.55) 0 6px, transparent 6px 10px)',
          }}
        />

        {days.map(d => (
          <div key={d} className="absolute top-5 h-4 border-l border-white/10 pl-1 text-[10px] whitespace-nowrap text-muted-foreground" style={{ left: pct(d, start, end) }}>
            <span className="num">{formatDay(d + IST_OFFSET / 2)}</span>
          </div>
        ))}

        {landfall && (
          <div
            className="absolute top-[9px] size-2.5 -translate-x-1/2 rotate-45 border border-[#E0B34A] bg-background"
            style={{ left: pct(landfall, start, end) }}
            title={`First observed track point over land · ${formatIST(landfall)}`}
          />
        )}

        {/* cutoff marker: draggable now-line */}
        <div
          role="slider"
          tabIndex={0}
          aria-label="Bulletin cutoff"
          aria-valuenow={cutoff}
          aria-valuetext={formatIST(cutoff)}
          onPointerDown={e => drag(e, moveCutoff)}
          onKeyDown={e => {
            if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
              e.stopPropagation()
              e.preventDefault()
              clockActions.setCutoff(cutoff + (e.key === 'ArrowLeft' ? -CUTOFF_STEP : CUTOFF_STEP))
            }
          }}
          className="group absolute -top-1 bottom-0 z-10 w-4 -translate-x-1/2 cursor-ew-resize outline-none"
          style={{ left: pct(cutoff, start, end) }}
        >
          <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-foreground/80" />
          <div className="num absolute -top-0.5 left-1/2 -translate-x-1/2 rounded-sm bg-foreground px-1 text-[9px] leading-3 font-semibold tracking-wider text-background group-focus-visible:ring-2 group-focus-visible:ring-ring">
            NOW
          </div>
        </div>

        {/* playhead */}
        <div ref={headRef} className="pointer-events-none absolute top-1 bottom-2 z-20 w-0">
          <div className="absolute inset-y-0 w-0.5 -translate-x-1/2 rounded-full bg-primary" />
          <div className="absolute top-[7px] size-3 -translate-x-1/2 rounded-full border-2 border-primary bg-background" />
        </div>
      </div>
    </section>
  )
}
