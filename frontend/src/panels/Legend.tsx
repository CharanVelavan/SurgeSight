import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { RAIN_RAMP, RISK, WIND_RAMP, rampCss } from '@/lib/colors'
import { formatCycle } from '@/lib/format'
import { SURFACE } from '@/weather/surface'
import { useTimeline } from '@/app/queries'
import { INFRA_ZOOM } from '@/map/assetLayers'
import { ZONE_HEX } from '@/alerts/field'
import { t, useT, type Key } from '@/i18n'
import { useUi } from '@/state/ui'
import { useClock } from '@/timeline/clock'
import { rainField, windField, type FieldPair } from '@/weather/field'
import { useWeather } from '@/weather/useWeather'

function sourceLabel(p: FieldPair | null, what: 'wind' | 'rain'): string {
  if (!p) return t(what === 'wind' ? 'key.noForecast' : 'key.noData')
  if (p.kind === 'forecast') return t('key.src.forecast', { cycle: formatCycle(Date.parse(p.cycle!)) })
  return t(`key.src.${p.kind}` as Key)
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
  const t = useT()
  const { wind, rain, rainSource, zones, mode, field } = useUi()
  const live = mode === 'live'
  const manifest = useWeather(s => s.manifest)
  const { time, cutoff } = useClock(s => ({ time: Math.floor(s.time / 3_600_000), cutoff: s.cutoff }), 250)
  const { data: timeline } = useTimeline()
  // Open by default from 640 px up; on phones it starts collapsed so it does not cover the storm.
  const [open, setOpen] = useState(() => matchMedia('(min-width: 640px)').matches)
  const anyInfra = useUi(s => s.mode === 'replay' && Object.values(s.infra).some(Boolean) && s.zoom >= INFRA_ZOOM)
  if (!manifest || (!zones && !wind && !rain && !anyInfra && field === 'none')) return null
  const ms = time * 3_600_000
  const w = windField(manifest, ms, cutoff)
  const r = rainField(manifest, ms, cutoff, rainSource)
  return (
    <section aria-label={t('key.title')} className="panel pointer-events-auto absolute bottom-[132px] left-3 z-10 flex w-72 flex-col gap-2.5 p-3 max-sm:bottom-[140px] max-sm:w-[calc(100%-24px)]">
      <button type="button" onClick={() => setOpen(o => !o)} aria-expanded={open} className="flex items-center justify-between text-[10px] font-medium tracking-[0.14em] text-muted-foreground uppercase sm:hidden">
        {t('key.title')}
        <ChevronDown className={`size-4 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      <div className="hidden text-[10px] font-medium tracking-[0.14em] text-muted-foreground uppercase sm:block">{t('key.title')}</div>
      <div className={`flex flex-col gap-2.5 ${open ? '' : 'max-sm:hidden'}`}>
      {!live && <div>
        <div className="flex items-baseline justify-between text-[11px]">
          <span className="font-medium">{t('key.storm')}</span>
          <span className="text-muted-foreground">{timeline?.cyclone ?? ''}</span>
        </div>
        <p className="mt-1 text-[10px] leading-snug text-muted-foreground">
          {t('key.stormText')}
        </p>
      </div>}
      {zones && (
        <div>
          <div className="flex items-baseline justify-between text-[11px]">
            <span className="font-medium">{t('key.zones')}</span>
            <span className="text-muted-foreground">{t('key.zonesSub')}</span>
          </div>
          <div className="mt-1 flex gap-3 text-[11px]">
            {(['safe', 'watch', 'warning', 'severe'] as const).map((name, i) => (
              <span key={name} className="flex items-center gap-1">
                <span className="inline-block size-2.5 rounded-sm" style={{ background: ZONE_HEX[i] }} aria-hidden />
                {t(`key.${name}` as Key)}
              </span>
            ))}
          </div>
          <p className="mt-1 text-[10px] leading-snug text-muted-foreground">{t('key.zonesNotice')}</p>
        </div>
      )}
      {field !== 'none' && (
        <Scale title={t(`field.${field}` as Key)} unit={SURFACE[field].unit} stops={SURFACE[field].stops} gradient={rampCss(SURFACE[field].ramp.map(([v, h, a]) => [v, h, Math.max(a ?? 1, 0.6)] as const))} note={t('key.src.forecast', { cycle: live && manifest.live ? formatCycle(Date.parse(manifest.live.cycle)) : '' })} />
      )}
      {wind && (
        <Scale title={t('key.wind')} unit="m/s" stops={WIND_RAMP.map(([v]) => v)} gradient={rampCss(WIND_RAMP)} note={sourceLabel(w, 'wind')} warn={!w} />
      )}
      {rain && (
        <Scale
          title={t('key.rain')}
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
            <span className="font-medium">{t('key.infra')}</span>
            <span className="text-muted-foreground">{t('key.infraSub', { when: timeline ? formatCycle(Date.parse(timeline.demo_cutoff.replace(' ', 'T') + 'Z')) : '' })}</span>
          </div>
          <div className="mt-1 flex gap-3 text-[11px]">
            {(['MODERATE', 'HIGH', 'CRITICAL'] as const).map(c => (
              <span key={c} className="flex items-center gap-1">
                <span style={{ color: RISK[c].color }} aria-hidden>{RISK[c].symbol}</span>
                {t(`risk.${c}` as Key)}
              </span>
            ))}
          </div>
        </div>
      )}
      <p className="border-t border-white/10 pt-2 text-[10px] leading-snug text-muted-foreground">{t('key.official')}</p>
      </div>
    </section>
  )
}
