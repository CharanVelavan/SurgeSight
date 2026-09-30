import { RAIN_RAMP, RISK, WIND_RAMP, rampCss } from '@/lib/colors'
import { formatCycle } from '@/lib/format'
import { useTimeline } from '@/app/queries'
import { useUi } from '@/state/ui'
import { useClock } from '@/timeline/clock'
import { rainField, windField, type FieldPair } from '@/weather/field'
import { useWeather } from '@/weather/useWeather'

function sourceLabel(p: FieldPair | null, what: 'wind' | 'rain'): string {
  if (!p) return what === 'wind' ? 'no GFS forecast this far ahead' : 'no data at this time'
  switch (p.kind) {
    case 'analysis':
      return 'GFS analysis'
    case 'observed':
      return 'IMERG observed'
    case 'validation':
      return 'IMERG observed · validation only'
    case 'forecast':
      return `GFS forecast issued ${formatCycle(Date.parse(p.cycle!))}`
  }
}

function Scale({ title, unit, stops, gradient, note, warn }: { title: string; unit: string; stops: number[]; gradient: string; note: string; warn?: boolean }) {
  return (
    <div>
      <div className="flex items-baseline justify-between text-[11px]">
        <span className="font-medium">{title}</span>
        <span className={warn ? 'text-[#E0B34A]' : 'text-muted-foreground'}>{note}</span>
      </div>
      <div className="mt-1 h-1.5 rounded-full" style={{ background: gradient }} />
      <div className="num mt-0.5 flex justify-between text-[10px] text-muted-foreground">
        {stops.map(s => (
          <span key={s}>{s}</span>
        ))}
        <span>{unit}</span>
      </div>
    </div>
  )
}

export function Legend() {
  const { wind, rain, rainSource } = useUi()
  const manifest = useWeather(s => s.manifest)
  const { time, cutoff } = useClock(s => ({ time: Math.floor(s.time / 3_600_000), cutoff: s.cutoff }), 250)
  const { data: timeline } = useTimeline()
  const anyInfra = useUi(s => Object.values(s.infra).some(Boolean))
  if (!manifest || (!wind && !rain && !anyInfra)) return null
  const ms = time * 3_600_000
  const w = windField(manifest, ms, cutoff)
  const r = rainField(manifest, ms, cutoff, rainSource)
  return (
    <section aria-label="Legend" className="panel pointer-events-auto absolute bottom-[132px] left-3 z-10 flex w-72 flex-col gap-2.5 p-3 max-sm:bottom-[140px] max-sm:w-[calc(100%-24px)]">
      {wind && (
        <Scale title="Wind" unit="m/s" stops={WIND_RAMP.map(([v]) => v)} gradient={rampCss(WIND_RAMP)} note={sourceLabel(w, 'wind')} warn={!w} />
      )}
      {rain && (
        <Scale
          title="Rain"
          unit="mm/h"
          stops={RAIN_RAMP.slice(1).map(([v]) => v)}
          gradient={rampCss(RAIN_RAMP.slice(1))}
          note={sourceLabel(r, 'rain')}
          warn={r?.kind === 'validation' || !r}
        />
      )}
      {anyInfra && (
        <div>
          <div className="flex items-baseline justify-between text-[11px]">
            <span className="font-medium">Infrastructure risk</span>
            <span className="text-muted-foreground">screening for the {timeline ? formatCycle(Date.parse(timeline.demo_cutoff.replace(' ', 'T') + 'Z')) : ''} bulletin</span>
          </div>
          <div className="mt-1 flex gap-3 text-[11px]">
            {(['MODERATE', 'HIGH', 'CRITICAL'] as const).map(c => (
              <span key={c} className="flex items-center gap-1">
                <span style={{ color: RISK[c].color }} aria-hidden>{RISK[c].symbol}</span>
                {RISK[c].label}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
