import { useDeferredValue, useMemo, useState } from 'react'
import { MapPinned, Search } from 'lucide-react'
import { useStore } from 'zustand'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { FacilityIcon, LevelBadge, RiskBadge } from '@/components/badges'
import { Page } from '@/components/shell/AppShell'
import { useAssetLevels } from '@/alerts/levels'
import { useTimeline } from '@/app/queries'
import { usePrefs } from '@/app/prefs'
import { ASSET_ICON } from '@/data/assetIcon'
import { ASSET_ORDER, assetsStore, type AssetType } from '@/data/assets'
import { roleById } from '@/data/roles'
import { useT, type Key } from '@/i18n'
import { formatCycle, formatInt } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useUi } from '@/state/ui'
import { useClock } from '@/timeline/clock'
import { showOnMap } from './actions'

const PAGE = 50
const CLASS_RANK: Record<string, number> = { CRITICAL: 3, HIGH: 2, MODERATE: 1, LOW: 0 }

/** Every screened facility, searchable and filtered to the user's role by default. */
export function Facilities({ id }: { id: string }) {
  const t = useT()
  const data = useStore(assetsStore, s => s.data)
  const error = useStore(assetsStore, s => s.error)
  const role = roleById(usePrefs(s => s.role))
  const cutoff = useClock(s => s.cutoff, 300)
  const levels = useAssetLevels(cutoff, cutoff)
  const { data: tl } = useTimeline()
  const set = useUi(s => s.set)
  const [types, setTypes] = useState<Set<AssetType>>(() => new Set(role.types))
  const [minClass, setMinClass] = useState('ALL')
  const [query, setQuery] = useState('')
  const [shown, setShown] = useState(PAGE)
  const q = useDeferredValue(query.trim().toLowerCase())

  const rows = useMemo(() => {
    if (!data) return []
    const min = minClass === 'ALL' ? -1 : CLASS_RANK[minClass]
    const out: number[] = []
    for (let i = 0; i < data.count; i++) {
      if (!types.has(data.type[i] as AssetType)) continue
      if ((CLASS_RANK[data.riskClass[i]] ?? 0) < min) continue
      if (q && !(data.name[i] || '').toLowerCase().includes(q)) continue
      out.push(i)
    }
    return out.sort((a, b) => {
      if (levels) {
        const diff = levels[b] - levels[a]
        if (diff !== 0) return diff
      }
      return data.riskScore[b] - data.riskScore[a]
    })
  }, [data, types, minClass, q, levels])

  const mine = role.types.length === types.size && role.types.every(x => types.has(x))
  const toggle = (a: AssetType) => {
    const next = new Set(types)
    if (next.has(a)) next.delete(a)
    else next.add(a)
    setTypes(next)
    setShown(PAGE)
  }

  return (
    <Page>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input value={query} onChange={e => { setQuery(e.target.value); setShown(PAGE) }} placeholder={t('facilities.search')} aria-label={t('facilities.search')} className="h-10 pl-9" />
        </div>
        <Select value={minClass} onValueChange={v => { setMinClass(v); setShown(PAGE) }}>
          <SelectTrigger aria-label={t('facilities.class')} className="h-10 sm:w-52"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">{t('facilities.allClasses')}</SelectItem>
            {(['CRITICAL', 'HIGH', 'MODERATE'] as const).map(c => (
              <SelectItem key={c} value={c}>{t('facilities.atLeast', { level: t(`risk.${c}` as Key) })}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5" role="group" aria-label={t('facilities.types')}>
        <button type="button" onClick={() => { setTypes(new Set(role.types)); setShown(PAGE) }} className={cn('rounded-full border border-border px-3 py-1 text-[12.5px] font-medium', mine && 'border-primary bg-primary text-primary-foreground')}>
          {t('facilities.mine')}
        </button>
        <button type="button" onClick={() => { setTypes(new Set(ASSET_ORDER)); setShown(PAGE) }} className={cn('rounded-full border border-border px-3 py-1 text-[12.5px] font-medium', types.size === ASSET_ORDER.length && 'border-primary bg-primary text-primary-foreground')}>
          {t('facilities.all')}
        </button>
        <span className="mx-1 h-5 w-px bg-border" aria-hidden />
        {ASSET_ORDER.map(a => {
          const Icon = ASSET_ICON[a]
          const on = types.has(a)
          return (
            <button key={a} type="button" aria-pressed={on} onClick={() => toggle(a)} className={cn('flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12.5px] transition-colors', on ? 'border-primary/50 bg-accent text-foreground' : 'border-border text-muted-foreground hover:text-foreground')}>
              <Icon className="size-3.5" aria-hidden /> {t(`asset.${a}` as Key)}
            </button>
          )
        })}
      </div>

      <p className="mt-4 text-[12.5px] text-muted-foreground" aria-live="polite">
        {t('facilities.count', { shown: formatInt(Math.min(shown, rows.length)), total: formatInt(rows.length) })}
        {' · '}
        {t('facilities.note', { when: tl ? formatCycle(Date.parse(tl.demo_cutoff.replace(' ', 'T') + 'Z')) : '' })}
      </p>

      <div className="mt-3 overflow-hidden rounded-xl border border-border bg-card">
        <div className="hidden grid-cols-[minmax(0,2.4fr)_minmax(0,1.2fr)_7rem_4rem_7rem_7.5rem] gap-3 border-b border-border bg-muted/50 px-4 py-2.5 text-[12px] font-medium text-muted-foreground md:grid">
          <span>{t('facilities.col.name')}</span>
          <span>{t('facilities.col.hazard')}</span>
          <span>{t('facilities.col.risk')}</span>
          <span className="text-right">{t('facilities.col.score')}</span>
          <span>{t('facilities.col.zone')}</span>
          <span className="sr-only">{t('facilities.col.actions')}</span>
        </div>
        {error && !data ? (
          <p role="alert" className="p-4 text-[13px] text-warn">{t('atrisk.error')}</p>
        ) : !data ? (
          <div className="space-y-2 p-4">{[0, 1, 2, 3, 4].map(i => <Skeleton key={i} className="h-11" />)}</div>
        ) : rows.length === 0 ? (
          <p className="p-8 text-center text-[13.5px] text-muted-foreground">{t('facilities.empty')}</p>
        ) : (
          <ul className="divide-y divide-border">
            {rows.slice(0, shown).map(i => (
              <li key={i} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 px-4 py-2.5 md:grid-cols-[minmax(0,2.4fr)_minmax(0,1.2fr)_7rem_4rem_7rem_7.5rem]">
                <button type="button" onClick={() => set({ selectedAsset: i })} className="flex min-w-0 items-center gap-3 text-left">
                  <FacilityIcon type={data.type[i]} cls={data.riskClass[i]} size="sm" />
                  <span className="min-w-0">
                    <span className="block truncate text-[13.5px] font-medium hover:underline">{data.name[i] || t('asset.unnamed')}</span>
                    <span className="block truncate text-[12px] text-muted-foreground">{t(`asset1.${data.type[i]}` as Key)}</span>
                  </span>
                </button>
                <span className="hidden truncate text-[13px] text-muted-foreground md:block">{t(`hazard.${data.hazard[i]}` as Key)}</span>
                <span className="justify-self-end md:justify-self-start"><RiskBadge cls={data.riskClass[i]} /></span>
                <span className="num hidden text-right text-[13px] md:block">{data.riskScore[i].toFixed(2)}</span>
                <span className="md:block"><LevelBadge level={levels?.[i]} /></span>
                <span className="flex justify-end gap-1">
                  <Button variant="ghost" size="sm" onClick={() => set({ selectedAsset: i })}>{t('facilities.why')}</Button>
                  <Button variant="ghost" size="icon-sm" onClick={() => showOnMap(id, i)} aria-label={t('facilities.onMap')} title={t('facilities.onMap')}>
                    <MapPinned className="size-4" />
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {rows.length > shown && (
        <div className="mt-4 flex justify-center">
          <Button variant="outline" onClick={() => setShown(s => s + PAGE)}>{t('facilities.more')}</Button>
        </div>
      )}
    </Page>
  )
}
