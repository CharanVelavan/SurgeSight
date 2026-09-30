import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Info, MapPinned, TrafficCone, Unplug } from 'lucide-react'
import { useStore } from 'zustand'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { AccessBadge, FacilityIcon, RoadLevelBadge } from '@/components/badges'
import { Page } from '@/components/shell/AppShell'
import { ZONE_HEX } from '@/alerts/field'
import { usePrefs } from '@/app/prefs'
import { assetsStore } from '@/data/assets'
import { ROAD_CLASSES, roadsStore } from '@/data/roads'
import { inRole, roleById } from '@/data/roles'
import { useT, type Key } from '@/i18n'
import { api } from '@/lib/api'
import { formatInt, formatNumber } from '@/lib/format'
import { useUi } from '@/state/ui'
import { observedRatio, showRoadOnMap, worstRoads } from './roadStats'

const LEVELS = ['most_exposed', 'high_exposure', 'watch'] as const
const LEVEL_NUM = { most_exposed: 3, high_exposure: 2, watch: 1 } as const
const ROWS = 12

/** Kilometres of main road by level, as three figures and one bar. */
function KmByLevel({ km, total }: { km: Record<string, number>; total: number }) {
  const t = useT()
  return (
    <section aria-label={t('roads.kmTitle')} className="rounded-xl border border-border bg-card p-4">
      <div className="grid gap-4 sm:grid-cols-3">
        {LEVELS.map(l => (
          <div key={l}>
            <RoadLevelBadge level={LEVEL_NUM[l]} />
            <div className="num mt-1.5 text-[22px] leading-tight font-semibold tracking-tight">{formatInt(km[l] ?? 0)} km</div>
          </div>
        ))}
      </div>
      <div className="mt-4 flex h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
        {LEVELS.map(l => <span key={l} style={{ width: `${((km[l] ?? 0) / total) * 100}%`, background: ZONE_HEX[LEVEL_NUM[l]] }} />)}
      </div>
      <p className="mt-2 text-[12.5px] text-muted-foreground">{t('roads.kmOf', { total: formatInt(total), open: formatInt(km.open ?? 0) })}</p>
    </section>
  )
}

/** The storm's main roads: how much is likely to flood or be blocked, which roads, and which facilities that cuts off. */
export function Roads({ id }: { id: string }) {
  const t = useT()
  const roads = useStore(roadsStore, s => s.data)
  const missing = useStore(roadsStore, s => s.missing)
  const assets = useStore(assetsStore, s => s.data)
  const role = roleById(usePrefs(s => s.role))
  const set = useUi(s => s.set)
  const [shown, setShown] = useState(ROWS)
  const summary = useQuery({ queryKey: ['roads-summary'], queryFn: api.roadSummary, staleTime: Infinity, retry: 0 })
  const rows = useMemo(() => (roads ? worstRoads(roads) : null), [roads])

  const cut = useMemo(() => {
    if (!assets) return null
    const out: number[] = []
    for (let i = 0; i < assets.count; i++) {
      const a = assets.roadAccess[i]
      if ((a === 'cut_off' || a === 'at_risk') && inRole(role, assets.type[i], assets.quality[i])) out.push(i)
    }
    const rank = (i: number) => (assets.roadAccess[i] === 'cut_off' ? 0 : 1)
    return out.sort((a, b) => rank(a) - rank(b) || assets.riskScore[b] - assets.riskScore[a])
  }, [assets, role])

  const ratio = summary.data ? observedRatio(summary.data) : null
  const districts = summary.data ? Object.entries(summary.data.km_level2plus_by_district).slice(0, 10) : null

  if (missing && !roads)
    return (
      <Page>
        <p role="alert" className="rounded-xl border border-border bg-card p-6 text-[14px] text-muted-foreground">{t('roads.missing')}</p>
      </Page>
    )

  return (
    <Page>
      <div>
        <h2 className="flex items-center gap-2 text-[20px] font-semibold tracking-tight"><TrafficCone className="size-5 text-primary" aria-hidden />{t('roads.title')}</h2>
        <p className="mt-1 max-w-3xl text-[13.5px] text-muted-foreground">{t('roads.lead')}</p>
      </div>

      <div className="mt-5">
        {summary.data ? <KmByLevel km={summary.data.km_by_level} total={summary.data.km_total} /> : <Skeleton className="h-36 rounded-xl" />}
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-5">
        <section aria-labelledby="worst" className="rounded-xl border border-border bg-card lg:col-span-3">
          <div className="border-b border-border p-4">
            <h3 id="worst" className="text-[15px] font-semibold">{t('roads.worst')}</h3>
            <p className="mt-0.5 text-[13px] text-muted-foreground">{t('roads.worstLead')}</p>
          </div>
          {!rows || !roads ? (
            <div className="space-y-2 p-4">{[0, 1, 2, 3, 4].map(i => <Skeleton key={i} className="h-11" />)}</div>
          ) : rows.length === 0 ? (
            <p className="p-6 text-center text-[13.5px] text-muted-foreground">{t('roads.noneWorst')}</p>
          ) : (
            <ul className="divide-y divide-border">
              {rows.slice(0, shown).map(r => (
                <li key={r.name} className="flex items-center gap-3 px-4 py-2.5">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13.5px] font-medium">{roads.cols.names[r.name]}</span>
                    <span className="block truncate text-[12px] text-muted-foreground">
                      {t(`road.class.${ROAD_CLASSES[r.highway]}` as Key)} · {t('roads.kmAffected', { km: formatNumber(r.km, 1) })}
                      {r.districts.length ? ` · ${r.districts.slice(0, 2).join(', ')}` : ''}
                    </span>
                  </span>
                  <RoadLevelBadge level={r.worst} className="max-sm:hidden" />
                  <Button variant="ghost" size="icon-sm" onClick={() => showRoadOnMap(id, roads, r.section)} aria-label={t('facilities.onMap')} title={t('facilities.onMap')}>
                    <MapPinned className="size-4" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
          {rows && rows.length > shown && (
            <div className="border-t border-border p-3 text-center">
              <Button variant="outline" size="sm" onClick={() => setShown(s => s + ROWS)}>{t('facilities.more')}</Button>
            </div>
          )}
        </section>

        <div className="flex flex-col gap-5 lg:col-span-2">
          <section aria-labelledby="cut" className="rounded-xl border border-border bg-card">
            <div className="border-b border-border p-4">
              <h3 id="cut" className="flex items-center gap-2 text-[15px] font-semibold"><Unplug className="size-4 text-primary" aria-hidden />{t('roads.cutTitle')}</h3>
              <p className="mt-0.5 text-[13px] text-muted-foreground">{t('roads.cutLead', { role: t(`role.${role.id}.name` as Key) })}</p>
            </div>
            {!cut || !assets ? (
              <div className="space-y-2 p-4">{[0, 1, 2].map(i => <Skeleton key={i} className="h-11" />)}</div>
            ) : cut.length === 0 ? (
              <p className="p-4 text-[13px] text-muted-foreground">{t('roads.cutNone')}</p>
            ) : (
              <ul className="max-h-[26rem] divide-y divide-border overflow-y-auto">
                {cut.slice(0, 40).map(i => {
                  const before = assets.hospitalKmBefore[i], after = assets.hospitalKmAfter[i]
                  return (
                    <li key={i}>
                      <button type="button" onClick={() => set({ selectedAsset: i })} className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-accent/60">
                        <FacilityIcon type={assets.type[i]} cls={assets.riskClass[i]} size="sm" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13.5px] font-medium">{assets.name[i] || t('asset.unnamed')}</span>
                          <span className="block truncate text-[12px] text-muted-foreground">
                            {assets.type[i] === 'hospital' || before === null
                              ? t(`asset1.${assets.type[i]}` as Key)
                              : after === null
                                ? t('access.noHospital')
                                : t('access.hospitalTrip', { before: formatNumber(before, 1), after: formatNumber(after, 1) })}
                          </span>
                        </span>
                        <AccessBadge access={assets.roadAccess[i]} />
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
            {cut && cut.length > 40 && <p className="border-t border-border px-4 py-2 text-[12px] text-muted-foreground">{t('roads.cutMore', { n: formatInt(cut.length - 40) })}</p>}
          </section>

          <section aria-labelledby="bydist" className="rounded-xl border border-border bg-card">
            <h3 id="bydist" className="border-b border-border p-4 text-[15px] font-semibold">{t('roads.byDistrict')}</h3>
            {!districts ? (
              <div className="space-y-2 p-4">{[0, 1, 2].map(i => <Skeleton key={i} className="h-7" />)}</div>
            ) : (
              <ul className="divide-y divide-border text-[13.5px]">
                {districts.map(([name, km]) => (
                  <li key={name} className="flex items-center justify-between gap-3 px-4 py-2">
                    <span className="truncate">{name}</span>
                    <span className="num shrink-0 font-medium">{formatInt(km)} km</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>

      <section aria-labelledby="how" className="mt-5 rounded-xl border border-border bg-card p-4">
        <h3 id="how" className="flex items-center gap-2 text-[15px] font-semibold"><Info className="size-4 text-primary" aria-hidden />{t('roads.howTitle')}</h3>
        <ul className="mt-2.5 flex list-disc flex-col gap-1.5 pl-5 text-[13px] leading-relaxed text-muted-foreground">
          <li>{t('roads.how1')}</li>
          <li>{t('roads.how2')}</li>
          <li>{t('roads.how3')}</li>
          {ratio && <li>{t('road.checked', ratio)}</li>}
          <li>{t('roads.how4')}</li>
        </ul>
      </section>
    </Page>
  )
}
