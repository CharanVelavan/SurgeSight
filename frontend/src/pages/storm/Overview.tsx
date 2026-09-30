import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Compass, Landmark, Gauge, MapPinned, Navigation, ShieldAlert, Waves } from 'lucide-react'
import { useStore } from 'zustand'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { BulletinSelect } from '@/components/BulletinSelect'
import { FacilityIcon, LevelBadge, RiskBadge } from '@/components/badges'
import { Page } from '@/components/shell/AppShell'
import { areaRows, levelGrid, useAssetLevels, useDistricts } from '@/alerts/levels'
import { useTimeline } from '@/app/queries'
import { Link, pathFor } from '@/app/router'
import { usePrefs } from '@/app/prefs'
import { assetsStore } from '@/data/assets'
import { inRole, priorityRank, roleById } from '@/data/roles'
import { useT, type Key } from '@/i18n'
import { api } from '@/lib/api'
import { compass, formatInt, formatIST, formatLatLon } from '@/lib/format'
import { stormStatus } from '@/lib/storm'
import { useUi } from '@/state/ui'
import { useClock } from '@/timeline/clock'
import { useWeather } from '@/weather/useWeather'

const crore = (v: number) => `₹${formatInt(v)} cr`

/** Illustrative parametric cover: which triggers the forecast breaches and what would pay out, before landfall. */
function Parametric() {
  const t = useT()
  const { data, isPending, isError } = useQuery({ queryKey: ['parametric'], queryFn: api.parametric, staleTime: Infinity, retry: 0 })
  const p = data?.data
  return (
    <section aria-labelledby="param" className="mt-5 rounded-xl border border-border bg-card">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border p-4">
        <div>
          <h2 id="param" className="flex items-center gap-2 text-[15px] font-semibold"><Landmark className="size-4 text-primary" aria-hidden />{t('param.title')}</h2>
          <p className="mt-0.5 max-w-2xl text-[13px] text-muted-foreground">{t('param.lead')}</p>
        </div>
        {p && (
          <div className="text-right">
            <div className="num text-[20px] font-semibold">{crore(p.total_payout_crore)}</div>
            <div className="text-[12px] text-muted-foreground">{t('param.of', { total: crore(p.total_sum_insured_crore) })}</div>
          </div>
        )}
      </div>
      {isPending ? (
        <div className="grid gap-3 p-4 md:grid-cols-2">{[0, 1].map(i => <Skeleton key={i} className="h-24" />)}</div>
      ) : isError || !p ? (
        <p role="alert" className="p-4 text-[13px] text-warn">{t('param.error')}</p>
      ) : (
        <ul className="grid gap-px bg-border md:grid-cols-2">
          {p.portfolios.map(pf => (
            <li key={pf.id} className="bg-card p-4">
              <div className="flex items-start justify-between gap-3">
                <span className="text-[13.5px] font-medium">{pf.districts.join(', ')}</span>
                <span className="num shrink-0 text-[13.5px] font-semibold">{crore(pf.payout_crore)}</span>
              </div>
              <ul className="mt-2 flex flex-col gap-1 text-[12.5px]">
                {pf.triggers.map(tr => (
                  <li key={tr.id} className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-1.5 text-muted-foreground">
                      <span aria-hidden className={`inline-block size-2 rounded-full ${tr.breached ? 'bg-destructive' : 'bg-muted-foreground/40'}`} />
                      {['wind', 'rain_24h', 'surge'].includes(tr.id) ? t(`param.trig.${tr.id}` as Key) : tr.label}
                    </span>
                    <span className="num">{tr.breached ? t('param.breached', { pct: tr.payout_pct }) : t('param.notBreached')}</span>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
      <p className="border-t border-border px-4 py-2.5 text-[11.5px] leading-snug text-muted-foreground">{t('param.note')}</p>
    </section>
  )
}

function Stat({ icon: Icon, label, value, note, tone }: { icon: typeof Gauge; label: string; value: React.ReactNode; note?: React.ReactNode; tone?: 'warn' }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
        <Icon className="size-4" aria-hidden /> {label}
      </div>
      <div className={`mt-2 text-[20px] leading-tight font-semibold tracking-tight ${tone === 'warn' ? 'text-warn' : ''}`}>{value}</div>
      {note && <div className="mt-1 text-[12.5px] text-muted-foreground">{note}</div>}
    </div>
  )
}

export function Overview({ id }: { id: string }) {
  const t = useT()
  const { data: tl } = useTimeline()
  const cutoff = useClock(s => s.cutoff, 200)
  const role = roleById(usePrefs(s => s.role))
  const data = useStore(assetsStore, s => s.data)
  const levels = useAssetLevels(cutoff, cutoff)
  const weatherReady = useWeather(s => s.total > 0 && s.loaded >= s.total)
  const { data: districts } = useDistricts()
  const set = useUi(s => s.set)
  const status = tl ? stormStatus(tl, cutoff) : null

  const mine = useMemo(() => {
    if (!data) return null
    const rows: number[] = []
    for (let i = 0; i < data.count; i++) if (inRole(role, data.type[i], data.quality[i])) rows.push(i)
    rows.sort((a, b) => priorityRank(data.type[a], data.quality[a]) - priorityRank(data.type[b], data.quality[b]) || data.riskScore[b] - data.riskScore[a])
    return rows
  }, [data, role])

  const alerted = levels ? levels.reduce((n, l) => n + (l >= 2 ? 1 : 0), 0) : null
  const areas = useMemo(() => {
    if (!districts || !weatherReady || !data) return null
    return areaRows(districts, levelGrid(cutoff, cutoff)).sort((a, b) => b.level - a.level || b.critical + b.high - (a.critical + a.high)).slice(0, 5)
  }, [districts, weatherReady, data, cutoff])

  const landfall = status?.landfallInH
  return (
    <Page>
      <div className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4 sm:flex-row sm:items-center">
        <div className="flex-1">
          <h2 className="text-[14px] font-semibold">{t('overview.bulletin')}</h2>
          <p className="mt-0.5 text-[13px] text-muted-foreground">{t('overview.bulletinHint')}</p>
        </div>
        <BulletinSelect />
      </div>

      <section aria-label={t('overview.storm')} className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {status ? (
          <>
            <Stat icon={Gauge} label={t('overview.storm')} value={t(`imd.${status.cls.short}` as Key)} note={`${t('overview.maxWind')} ${Math.round(status.windKmh)} km/h · ${Math.round(status.pressure)} hPa`} />
            <Stat
              icon={Compass}
              label={t('overview.position')}
              value={<span className="num text-[17px]">{formatLatLon(status.lat, status.lon)}</span>}
              note={status.headingDeg !== null && status.speedKmh !== null ? t('overview.moving', { dir: compass(status.headingDeg), speed: Math.round(status.speedKmh) }) : undefined}
            />
            <Stat
              icon={Navigation}
              label={t('overview.landfall')}
              value={landfall == null ? '—' : landfall > 0 ? t('overview.landfallIn', { h: landfall }) : t('overview.landfallDone', { h: -landfall })}
              note={t('overview.landfallNote')}
              tone={landfall != null && landfall > 0 && landfall <= 24 ? 'warn' : undefined}
            />
            <Stat
              icon={ShieldAlert}
              label={t('overview.alerts')}
              value={alerted === null ? <Skeleton className="h-6 w-16" /> : <span className="num">{formatInt(alerted)}</span>}
              note={t('overview.alertsNote')}
              tone={alerted ? 'warn' : undefined}
            />
          </>
        ) : (
          [0, 1, 2, 3].map(i => <Skeleton key={i} className="h-28 rounded-xl" />)
        )}
      </section>

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <section aria-labelledby="prio" className="rounded-xl border border-border bg-card lg:col-span-2">
          <div className="flex items-start justify-between gap-3 border-b border-border p-4">
            <div>
              <h2 id="prio" className="flex items-center gap-2 text-[15px] font-semibold">
                <role.icon className="size-4 text-primary" aria-hidden />
                {t('overview.priorities')}
              </h2>
              <p className="mt-0.5 text-[13px] text-muted-foreground">{t('overview.prioritiesLead', { role: t(`role.${role.id}.name` as Key) })}</p>
            </div>
            <Link to={pathFor({ name: 'storm', id, tab: 'facilities' })} className="shrink-0 text-[13px] font-medium text-primary hover:underline">{t('overview.seeAll')}</Link>
          </div>
          {!mine || !data ? (
            <div className="space-y-2 p-4">{[0, 1, 2, 3].map(i => <Skeleton key={i} className="h-12" />)}</div>
          ) : mine.length === 0 ? (
            <p className="p-4 text-[13px] text-muted-foreground">{t('overview.none')}</p>
          ) : (
            <ul className="divide-y divide-border">
              {mine.slice(0, 8).map(i => (
                <li key={i}>
                  <button type="button" onClick={() => set({ selectedAsset: i })} className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-accent/60">
                    <FacilityIcon type={data.type[i]} cls={data.riskClass[i]} size="sm" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13.5px] font-medium">{data.name[i] || t('asset.unnamed')}</span>
                      <span className="block truncate text-[12px] text-muted-foreground">
                        {t(`asset1.${data.type[i]}` as Key)} · {t(`hazard.${data.hazard[i]}` as Key)}
                      </span>
                    </span>
                    <LevelBadge level={levels?.[i]} className="max-sm:hidden" />
                    <RiskBadge cls={data.riskClass[i]} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="flex flex-col gap-5">
          <section aria-labelledby="q" className="rounded-xl border border-border bg-card p-4">
            <h2 id="q" className="text-[15px] font-semibold">{t('overview.questions')}</h2>
            <ul className="mt-3 flex flex-col gap-2.5 text-[13.5px] leading-snug">
              {(['q1', 'q2'] as const).map(q => (
                <li key={q} className="flex gap-2.5">
                  <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary" aria-hidden />
                  {t(`role.${role.id}.${q}` as Key)}
                </li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="areas" className="rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between border-b border-border p-4">
              <h2 id="areas" className="flex items-center gap-2 text-[15px] font-semibold"><Waves className="size-4 text-primary" aria-hidden />{t('overview.areas')}</h2>
              <Link to={pathFor({ name: 'storm', id, tab: 'areas' })} className="text-[13px] font-medium text-primary hover:underline">{t('overview.seeAreas')}</Link>
            </div>
            {!areas ? (
              <div className="space-y-2 p-4">{[0, 1, 2].map(i => <Skeleton key={i} className="h-8" />)}</div>
            ) : (
              <ul className="divide-y divide-border">
                {areas.map(a => (
                  <li key={a.district.name} className="flex items-center justify-between gap-3 px-4 py-2.5 text-[13.5px]">
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{a.district.name}</span>
                      <span className="block text-[12px] text-muted-foreground">{a.district.state}</span>
                    </span>
                    <LevelBadge level={a.level} />
                  </li>
                ))}
              </ul>
            )}
          </section>

          <Button asChild size="lg" className="w-full">
            <Link to={pathFor({ name: 'storm', id, tab: 'map' })}>
              <MapPinned className="size-4" /> {t('overview.openMap')} <ArrowRight className="ml-auto size-4" />
            </Link>
          </Button>
        </div>
      </div>
      <Parametric />
      <p className="mt-6 text-[12px] text-muted-foreground">{t('overview.asOf', { time: formatIST(cutoff) })}</p>
    </Page>
  )
}
