import { useQuery } from '@tanstack/react-query'
import { MapPinned, X } from 'lucide-react'
import { useStore } from 'zustand'
import { Button } from '@/components/ui/button'
import { ZONE_HEX } from '@/alerts/field'
import { RoadLevelBadge } from '@/components/badges'
import { ROAD_CLASSES, roadName, roadsStore } from '@/data/roads'
import { useT, type Key } from '@/i18n'
import { api } from '@/lib/api'
import { formatNumber } from '@/lib/format'
import { observedRatio } from '@/pages/storm/roadStats'

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 border-b border-border py-2 text-[13px] last:border-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="num text-right font-medium">{value}</dd>
    </div>
  )
}

/** One road section: its level, the main cause, and the numbers behind it. */
export function RoadDetails({ index, onClose, onShowOnMap }: { index: number; onClose?: () => void; onShowOnMap?: () => void }) {
  const t = useT()
  const d = useStore(roadsStore, s => s.data)
  const { data: summary } = useQuery({ queryKey: ['roads-summary'], queryFn: api.roadSummary, staleTime: Infinity, retry: 0 })
  if (!d || index >= d.count) return null
  const c = d.cols
  const cls = ROAD_CLASSES[c.highway[index]] ?? 'tertiary'
  const name = roadName(d, index)
  const level = c.level[index]
  const cause = c.cause[index]
  const na = t('why.notAvailable')
  const num = (v: number | null, unit: string, digits = 0) => (v === null ? na : `${formatNumber(v, digits)} ${unit}`)
  const reasons: string[] = []
  if (cause === 'flood') {
    if (c.elevation_min_m[index] !== null && c.elevation_min_m[index]! <= 10) reasons.push(t('road.why.low', { m: formatNumber(c.elevation_min_m[index]!, 0) }))
    if (c.hand_min_m[index] !== null && c.hand_min_m[index]! <= 3) reasons.push(t('road.why.drain', { m: formatNumber(c.hand_min_m[index]!, 1) }))
    if (c.rain_mm[index] !== null) reasons.push(t('road.why.rain', { mm: formatNumber(c.rain_mm[index]!, 0) }))
  }
  if (cause === 'surge' && c.surge_m[index] !== null) reasons.push(t('road.why.surge', { m: formatNumber(c.surge_m[index]!, 2) }))
  if (c.wind_kmh[index] !== null && c.wind_kmh[index]! >= 62) reasons.push(t('road.why.wind', { kmh: formatNumber(c.wind_kmh[index]!, 0) }))
  const ratio = summary ? observedRatio(summary) : null
  return (
    <section aria-label={t('road.aria')} className="flex flex-col">
      <div className="flex items-start gap-3">
        <span aria-hidden className="mt-1 h-1.5 w-8 shrink-0 rounded-full" style={{ background: ZONE_HEX[level] }} />
        <div className="min-w-0 flex-1">
          <h2 className="text-[16px] leading-snug font-semibold">{name ?? t('road.unnamed')}</h2>
          <p className="text-[13px] text-muted-foreground">
            {t(`road.class.${cls}` as Key)}
            {c.district[index] ? ` · ${c.district[index]}` : ''}
          </p>
        </div>
        {onClose && (
          <button type="button" onClick={onClose} aria-label={t('why.close')} className="-mt-1 -mr-1 grid size-8 shrink-0 place-items-center rounded-md text-muted-foreground hover:bg-accent">
            <X className="size-4" />
          </button>
        )}
      </div>

      <div className="mt-4 rounded-lg border border-border bg-background/50 p-3">
        <RoadLevelBadge level={level} />
        <p className="mt-1.5 text-[12.5px] text-muted-foreground">{t('road.causeLine', { cause: t(`road.cause.${cause}` as Key) })}</p>
        {reasons.length > 0 && (
          <ul className="mt-2.5 list-disc space-y-1 pl-4 text-[13px] leading-snug">
            {reasons.map(r => <li key={r}>{r}</li>)}
          </ul>
        )}
      </div>

      {onShowOnMap && (
        <Button variant="outline" onClick={onShowOnMap} className="mt-4 self-start">
          <MapPinned className="size-4" /> {t('facilities.onMap')}
        </Button>
      )}

      <h3 className="eyebrow mt-5 mb-1">{t('why.numbers')}</h3>
      <dl>
        <Row label={t('road.row.length')} value={num(c.km[index], 'km', 2)} />
        <Row label={t('road.row.lowest')} value={num(c.elevation_min_m[index], 'm')} />
        <Row label={t('road.row.hand')} value={num(c.hand_min_m[index], 'm', 1)} />
        <Row label={t('road.row.rain')} value={num(c.rain_mm[index], 'mm')} />
        <Row label={t('road.row.wind')} value={num(c.wind_kmh[index], 'km/h')} />
        <Row label={t('road.row.surge')} value={c.surge_m[index] ? num(c.surge_m[index], 'm', 2) : t('road.row.noSurge')} />
      </dl>
      <p className="mt-4 text-[11.5px] leading-snug text-muted-foreground">{t('road.method')}</p>
      {ratio && <p className="mt-1 text-[11.5px] leading-snug text-muted-foreground">{t('road.checked', ratio)}</p>}
      <p className="mt-1 text-[11.5px] leading-snug text-muted-foreground">{t('why.disclaimer')}</p>
    </section>
  )
}
