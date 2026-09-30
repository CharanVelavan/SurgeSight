import { useMemo, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { useStore } from 'zustand'
import { assetsStore, type AssetType } from '@/data/assets'
import { useT, type Key } from '@/i18n'
import { RISK, type RiskClass } from '@/lib/colors'
import { formatInt } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useUi } from '@/state/ui'

const CLASSES: RiskClass[] = ['CRITICAL', 'HIGH', 'MODERATE']
const TOP = 8

/** Read-only summary of the screened infrastructure: counts by risk class and the highest-scoring assets. */
export function AtRisk() {
  const t = useT()
  const data = useStore(assetsStore, s => s.data)
  const infra = useUi(s => s.infra)
  const set = useUi(s => s.set)
  const selected = useUi(s => s.selectedAsset)
  const [open, setOpen] = useState(true)

  const summary = useMemo(() => {
    if (!data) return null
    const counts: Record<string, number> = {}
    const rows: number[] = []
    for (let i = 0; i < data.count; i++) {
      if (!infra[data.type[i] as AssetType]) continue
      counts[data.riskClass[i]] = (counts[data.riskClass[i]] ?? 0) + 1
      rows.push(i)
    }
    rows.sort((a, b) => data.riskScore[b] - data.riskScore[a])
    return { counts, total: rows.length, top: rows.slice(0, TOP) }
  }, [data, infra])

  if (!summary || !data || selected !== null) return null
  const max = Math.max(1, ...CLASSES.map(c => summary.counts[c] ?? 0))

  return (
    <section aria-label={t('atrisk.aria')} className="panel pointer-events-auto absolute top-28 right-3 z-10 w-64 p-3 max-md:hidden">
      <button type="button" onClick={() => setOpen(o => !o)} className="flex w-full items-center justify-between text-left" aria-expanded={open}>
        <span>
          <span className="text-[10px] font-medium tracking-[0.14em] text-muted-foreground uppercase">{t('atrisk.title')}</span>
          <span className="num ml-2 text-[15px]">{formatInt(summary.total)}</span>
          <span className="ml-1 text-[11px] text-muted-foreground">{t('atrisk.assets')}</span>
        </span>
        <ChevronDown className={cn('size-4 text-muted-foreground transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <>
          <div className="mt-2.5 space-y-1.5">
            {CLASSES.map(c => (
              <div key={c} className="flex items-center gap-2 text-[12px]">
                <span className="w-4 text-center" style={{ color: RISK[c].color }} aria-hidden>{RISK[c].symbol}</span>
                <span className="w-16 text-muted-foreground">{t(`risk.${c}` as Key)}</span>
                <span className="h-1.5 flex-1 rounded-full bg-white/[0.06]">
                  <span className="block h-full rounded-full" style={{ width: `${((summary.counts[c] ?? 0) / max) * 100}%`, background: RISK[c].color }} />
                </span>
                <span className="num w-10 text-right">{formatInt(summary.counts[c] ?? 0)}</span>
              </div>
            ))}
          </div>

          <div className="mt-3 mb-1 text-[10px] font-medium tracking-[0.14em] text-muted-foreground uppercase">{t('atrisk.top')}</div>
          <ul className="-mx-1">
            {summary.top.map(i => {
              const cls = (data.riskClass[i] in RISK ? data.riskClass[i] : 'LOW') as RiskClass
              return (
                <li key={i}>
                  <button
                    type="button"
                    onClick={() => {
                      set({ view: 'impact', selectedAsset: i })
                      // the impact view re-frames first; the request then flies to the asset
                      setTimeout(() => set({ focus: { lon: data.lon[i], lat: data.lat[i], zoom: 12.5 } }), 60)
                    }}
                    className="flex w-full items-center gap-2 rounded-md px-1 py-1 text-left text-[12px] hover:bg-accent"
                  >
                    <span style={{ color: RISK[cls].color }} aria-hidden>{RISK[cls].symbol}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">{data.name[i] || t('asset.unnamed')}</span>
                      <span className="block truncate text-[11px] text-muted-foreground">{t(`asset1.${data.type[i]}` as Key)}</span>
                    </span>
                    <span className="num text-[11px] text-muted-foreground">{data.riskScore[i].toFixed(2)}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </>
      )}
    </section>
  )
}
