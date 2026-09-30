import { assetsStore } from '@/data/assets'
import { useT, type Key } from '@/i18n'
import { RISK, type RiskClass } from '@/lib/colors'
import { useUi } from '@/state/ui'
import { useStore } from 'zustand'

/** Name, class and dominant hazard for the marker under the pointer. Screening estimate, not an official warning. */
export function AssetPopover() {
  const t = useT()
  const i = useUi(s => s.hoverAsset)
  const cursor = useUi(s => s.cursor)
  const data = useStore(assetsStore, s => s.data)
  if (i === null || !data || !cursor) return null
  const cls = (data.riskClass[i] in RISK ? data.riskClass[i] : 'LOW') as RiskClass
  const type = t(`asset1.${data.type[i]}` as Key)
  const left = Math.min(cursor.x + 14, innerWidth - 250)
  const top = Math.min(cursor.y + 14, innerHeight - 130)
  return (
    <div className="panel pointer-events-none fixed z-30 w-56 px-3 py-2 text-[12px] leading-[18px]" style={{ left, top }}>
      <div className="truncate font-medium">{data.name[i] || t('asset.unnamed')}</div>
      <div className="text-muted-foreground">{type}</div>
      <div className="mt-1 flex items-center gap-1.5">
        <span style={{ color: RISK[cls].color }} aria-hidden>{RISK[cls].symbol}</span>
        <span>{t('risk.suffix', { level: t(`risk.${cls}` as Key) })}</span>
        <span className="num ml-auto text-muted-foreground">{data.riskScore[i].toFixed(2)}</span>
      </div>
      <div className="text-muted-foreground">
        {t('asset.mainHazard', { hazard: t(`hazard.${data.hazard[i]}` as Key), tier: data.tier[i] })}
      </div>
      <div className="mt-0.5 text-[11px] text-primary">{t('asset.clickWhy')}</div>
    </div>
  )
}
