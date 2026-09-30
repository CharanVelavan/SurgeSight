import { useMemo } from 'react'
import { Info } from 'lucide-react'
import { useStore } from 'zustand'
import { Skeleton } from '@/components/ui/skeleton'
import { BulletinSelect } from '@/components/BulletinSelect'
import { LevelBadge } from '@/components/badges'
import { Page } from '@/components/shell/AppShell'
import { areaRows, levelGrid, useDistricts } from '@/alerts/levels'
import { assetsStore } from '@/data/assets'
import { useT } from '@/i18n'
import { formatInt } from '@/lib/format'
import { useClock } from '@/timeline/clock'
import { useWeather } from '@/weather/useWeather'

/** Districts in the study area by their highest alert level at the bulletin time, with their facilities. */
export function Areas() {
  const t = useT()
  const cutoff = useClock(s => s.cutoff, 300)
  const { data: districts, isError } = useDistricts()
  const ready = useWeather(s => s.total > 0 && s.loaded >= s.total)
  const assets = useStore(assetsStore, s => s.data)
  const rows = useMemo(() => {
    if (!districts || !ready || !assets) return null
    return areaRows(districts, levelGrid(cutoff, cutoff)).sort((a, b) => b.level - a.level || b.critical + b.high - (a.critical + a.high) || a.district.name.localeCompare(b.district.name))
  }, [districts, ready, assets, cutoff])
  return (
    <Page>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
        <div className="flex-1">
          <h2 className="text-[20px] font-semibold tracking-tight">{t('areas.title')}</h2>
          <p className="mt-1 text-[13.5px] text-muted-foreground">{t('areas.lead')}</p>
        </div>
        <BulletinSelect />
      </div>

      <div className="mt-5 overflow-x-auto rounded-xl border border-border bg-card">
        <table className="w-full min-w-[640px] text-left text-[13.5px]">
          <thead className="border-b border-border bg-muted/50 text-[12px] text-muted-foreground">
            <tr>
              <th scope="col" className="px-4 py-2.5 font-medium">{t('areas.col.district')}</th>
              <th scope="col" className="px-4 py-2.5 font-medium">{t('areas.col.level')}</th>
              <th scope="col" className="px-4 py-2.5 text-right font-medium">{t('areas.col.population')}</th>
              <th scope="col" className="px-4 py-2.5 text-right font-medium">{t('areas.col.facilities')}</th>
              <th scope="col" className="px-4 py-2.5 text-right font-medium">{t('areas.col.critical')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isError ? (
              <tr><td colSpan={5} role="alert" className="p-4 text-warn">{t('areas.error')}</td></tr>
            ) : !rows ? (
              [0, 1, 2, 3, 4].map(i => (
                <tr key={i}><td colSpan={5} className="px-4 py-2"><Skeleton className="h-8" /></td></tr>
              ))
            ) : (
              rows.map(r => (
                <tr key={`${r.district.state}-${r.district.name}`}>
                  <th scope="row" className="px-4 py-2.5 font-medium">
                    {r.district.name}
                    <span className="block text-[12px] font-normal text-muted-foreground">{r.district.state}</span>
                  </th>
                  <td className="px-4 py-2.5"><LevelBadge level={r.level} /></td>
                  <td className="num px-4 py-2.5 text-right">{r.district.population === null ? '—' : formatInt(r.district.population)}</td>
                  <td className="num px-4 py-2.5 text-right">{formatInt(r.facilities)}</td>
                  <td className="num px-4 py-2.5 text-right font-medium">{formatInt(r.critical + r.high)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <p className="mt-4 flex gap-2 text-[12.5px] leading-relaxed text-muted-foreground">
        <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
        {t('areas.note', { n: districts?.length ?? '…' })}
      </p>
    </Page>
  )
}
