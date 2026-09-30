import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, MapPinned, Sparkles, X } from 'lucide-react'
import { useStore } from 'zustand'
import { Button } from '@/components/ui/button'
import { AccessBadge, FacilityIcon, LevelBadge, RiskBadge, riskClass } from '@/components/badges'
import { useAssetLevels } from '@/alerts/levels'
import { cutoffParam } from '@/app/queries'
import { assetsStore } from '@/data/assets'
import { currentApiLanguage, t as tt, useT, type Key } from '@/i18n'
import { api, type AssetFacts } from '@/lib/api'
import { formatIST, formatNumber } from '@/lib/format'
import { clock, useClock } from '@/timeline/clock'

const fmt = (v: number | null | undefined, unit: string) => (v === null || v === undefined ? tt('why.notAvailable') : `${v} ${unit}`)

function Row({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 border-b border-border py-2 text-[13px] last:border-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="num text-right font-medium">{value}</dd>
      {note && <dd className="col-span-2 mt-0.5 text-[11.5px] text-muted-foreground">{note}</dd>}
    </div>
  )
}

const NOTE_KEYS: Record<string, Key> = {
  'distance to the observed storm centre at the selected time': 'why.noteObserved',
  "the storm's position after the cutoff is a forecast, so no distance is given": 'why.noteForecast',
  'outside the observed track': 'why.noteOutside',
  'no time selected': 'why.noteNone',
}
const HAZARD_KEY: Record<string, string> = { wind: 'wind', 'storm surge': 'surge', 'rain flooding': 'rain_flood' }

function FactTable({ f, askedAt }: { f: AssetFacts; askedAt: number }) {
  const t = useT()
  const d = f.distance
  const noteKey = NOTE_KEYS[d.distance_at_time_note]
  return (
    <dl>
      <Row label={t('why.elevation')} value={f.elevation_m === null ? t('why.notAvailable') : t('why.elevationValue', { m: f.elevation_m })} />
      <Row label={t('why.waterlogging')} value={t(`why.level.${f.waterlogging.level}` as Key)} note={t('why.waterloggingNote', { mm: f.waterlogging.rain_forecast_mm ?? '—', score: f.waterlogging.terrain_flood_score ?? '—' })} />
      <Row label={t('why.wind')} value={fmt(f.wind_peak_kmh, 'km/h')} />
      <Row label={t('why.surge')} value={fmt(f.surge_m, 'm')} />
      <Row label={t('why.closest')} value={`${d.closest_approach_km} km`} note={t('why.closestAt', { time: d.closest_approach_time_utc.replace('T', ' ').replace('Z', '') })} />
      <Row label={t('why.distanceAt', { time: formatIST(askedAt) })} value={d.distance_at_time_km === null ? t('why.notShown') : `${d.distance_at_time_km} km`} note={noteKey ? t(noteKey) : d.distance_at_time_note} />
      <div className="py-2">
        <dt className="text-[13px] text-muted-foreground">{t('why.drives')}</dt>
        <dd className="mt-2 flex flex-col gap-1.5">
          {Object.entries(f.hazard_contributions).map(([k, v]) => (
            <div key={k} className="grid grid-cols-[7.5rem_1fr_2.5rem] items-center gap-2 text-[12px]">
              <span>{t(`hazard.${HAZARD_KEY[k] ?? 'none'}` as Key)}</span>
              <span className="h-1.5 rounded-full bg-muted"><span className="block h-full rounded-full bg-primary" style={{ width: `${Math.min(1, (v ?? 0) / 0.9) * 100}%` }} /></span>
              <span className="num text-right text-muted-foreground">{v}</span>
            </div>
          ))}
        </dd>
      </div>
    </dl>
  )
}

/**
 * One facility: what it is, its risk, the alert level where it stands now, and on request the facts behind
 * the ranking followed by a short written explanation (Gemini, checked against the facts).
 */
export function FacilityDetails({ index, onClose, onShowOnMap }: { index: number; onClose?: () => void; onShowOnMap?: () => void }) {
  const t = useT()
  const data = useStore(assetsStore, s => s.data)
  const { time, cutoff } = useClock(s => ({ time: s.time, cutoff: s.cutoff }), 500)
  const levels = useAssetLevels(time, cutoff)
  const [asked, setAsked] = useState<{ time: number; cutoff: number } | null>(null)
  useEffect(() => setAsked(null), [index])
  const key = data ? ([data.osmElement[index], data.osmId[index]] as const) : null
  const args = asked && key ? { time: cutoffParam(asked.time), cutoff: cutoffParam(asked.cutoff) } : null
  const lang = currentApiLanguage()
  const facts = useQuery({
    queryKey: ['why', key, args, false, lang],
    queryFn: () => api.explain(String(key![0]), Number(key![1]), args!.time, args!.cutoff, false, lang),
    enabled: !!args,
    staleTime: Infinity,
    retry: 0,
  })
  const text = useQuery({
    queryKey: ['why', key, args, true, lang],
    queryFn: () => api.explain(String(key![0]), Number(key![1]), args!.time, args!.cutoff, true, lang),
    enabled: !!args && facts.isSuccess,
    staleTime: Infinity,
    retry: 0,
  })
  if (!data) return null
  const cls = riskClass(data.riskClass[index])
  const critical = cls === 'CRITICAL' || cls === 'HIGH'
  return (
    <section aria-label={t('why.aria')} className="flex flex-col">
      <div className="flex items-start gap-3">
        <FacilityIcon type={data.type[index]} cls={cls} size="lg" />
        <div className="min-w-0 flex-1">
          <h2 className="text-[16px] leading-snug font-semibold">{data.name[index] || t('asset.unnamed')}</h2>
          <p className="text-[13px] text-muted-foreground">{t(`asset1.${data.type[index]}` as Key)}</p>
        </div>
        {onClose && (
          <button type="button" onClick={onClose} aria-label={t('why.close')} className="-mt-1 -mr-1 grid size-8 shrink-0 place-items-center rounded-md text-muted-foreground hover:bg-accent">
            <X className="size-4" />
          </button>
        )}
      </div>

      <dl className="mt-4 grid grid-cols-3 gap-2 rounded-lg border border-border bg-background/50 p-3 text-[12px]">
        <div>
          <dt className="text-muted-foreground">{t('facilities.col.risk')}</dt>
          <dd className="mt-1"><RiskBadge cls={cls} /></dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t('facilities.col.score')}</dt>
          <dd className="num mt-1 text-[14px] font-semibold">{data.riskScore[index].toFixed(2)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t('facilities.col.zone')}</dt>
          <dd className="mt-1"><LevelBadge level={levels?.[index]} /></dd>
        </div>
      </dl>
      <p className="mt-2 text-[12px] text-muted-foreground">
        {t('asset.mainHazard', { hazard: t(`hazard.${data.hazard[index]}` as Key), tier: data.tier[index] })}
      </p>

      {(data.roadAccess[index] === 'at_risk' || data.roadAccess[index] === 'cut_off') && (
        <div className="mt-3 rounded-lg border border-border bg-background/50 p-3">
          <AccessBadge access={data.roadAccess[index]} />
          <p className="mt-1.5 text-[12px] text-muted-foreground">
            {data.hospitalKmBefore[index] === null || data.hospitalKmAfter[index] === null
              ? t('access.noHospital')
              : t('access.hospitalTrip', { before: formatNumber(data.hospitalKmBefore[index]!, 1), after: formatNumber(data.hospitalKmAfter[index]!, 1) })}
          </p>
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        {!asked && (
          <Button onClick={() => setAsked({ time: clock.getState().time, cutoff: clock.getState().cutoff })}>
            <Sparkles className="size-4" />
            {critical ? t('why.button.critical') : t('why.button.notCritical')}
          </Button>
        )}
        {onShowOnMap && (
          <Button variant="outline" onClick={onShowOnMap}>
            <MapPinned className="size-4" /> {t('facilities.onMap')}
          </Button>
        )}
      </div>

      {asked && (
        <div className="mt-5">
          {facts.isPending && <p className="flex items-center gap-2 text-[13px] text-muted-foreground"><Loader2 className="size-4 animate-spin" aria-hidden />{t('why.working')}</p>}
          {facts.isError && <p role="alert" className="rounded-md bg-warn-bg p-3 text-[13px] text-warn">{t('why.error')}</p>}
          {facts.data && (
            <>
              <h3 className="eyebrow mb-1">{t('why.numbers')}</h3>
              <FactTable f={facts.data.facts} askedAt={asked.time} />
              <h3 className="eyebrow mt-5 mb-2">{t('why.words')}</h3>
              {text.isPending && <p className="flex items-center gap-2 text-[13px] text-muted-foreground"><Loader2 className="size-4 animate-spin" aria-hidden />{t('why.writing')}</p>}
              {text.isError && <p className="text-[13px] text-muted-foreground">{t('why.textError')}</p>}
              {text.data?.text && (
                <div className="rounded-lg bg-accent/60 p-3.5 text-[13.5px] leading-relaxed">
                  <p>{text.data.text.summary}</p>
                  {text.data.text.reasons.length > 0 && (
                    <ul className="mt-2 list-disc space-y-1 pl-4 text-muted-foreground">
                      {text.data.text.reasons.map((r, n) => <li key={n}>{r}</li>)}
                    </ul>
                  )}
                  <p className="mt-2.5 text-[11.5px] text-muted-foreground">{text.data.text_source === 'gemini' ? t('why.fromGemini') : t('why.fromTemplate')}</p>
                </div>
              )}
              <p className="mt-4 text-[11.5px] leading-snug text-muted-foreground">{t('why.source', { version: facts.data.facts.model_version })}</p>
              <p className="mt-1 text-[11.5px] leading-snug text-muted-foreground">{t('why.disclaimer')}</p>
            </>
          )}
        </div>
      )}
    </section>
  )
}
