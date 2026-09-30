import { assetsStore, ASSET_TYPES, type AssetType } from '@/data/assets'
import { RISK, type RiskClass } from '@/lib/colors'
import { useUi } from '@/state/ui'
import { useStore } from 'zustand'

const HAZARD: Record<string, string> = { wind: 'Wind', rain_flood: 'Rain flooding', surge: 'Storm surge', river: 'River flooding' }

/** Name, class and dominant hazard for the marker under the pointer. Screening estimate, not an official warning. */
export function AssetPopover() {
  const i = useUi(s => s.hoverAsset)
  const cursor = useUi(s => s.cursor)
  const data = useStore(assetsStore, s => s.data)
  if (i === null || !data || !cursor) return null
  const cls = (data.riskClass[i] in RISK ? data.riskClass[i] : 'LOW') as RiskClass
  const type = ASSET_TYPES[data.type[i] as AssetType]?.label.replace(/s$/, '') ?? data.type[i]
  const left = Math.min(cursor.x + 14, innerWidth - 250)
  const top = Math.min(cursor.y + 14, innerHeight - 130)
  return (
    <div className="panel pointer-events-none fixed z-30 w-56 px-3 py-2 text-[12px] leading-[18px]" style={{ left, top }}>
      <div className="truncate font-medium">{data.name[i] || 'Unnamed'}</div>
      <div className="text-muted-foreground">{type}</div>
      <div className="mt-1 flex items-center gap-1.5">
        <span style={{ color: RISK[cls].color }} aria-hidden>{RISK[cls].symbol}</span>
        <span>{RISK[cls].label} risk</span>
        <span className="num ml-auto text-muted-foreground">{data.riskScore[i].toFixed(2)}</span>
      </div>
      <div className="text-muted-foreground">
        Main hazard: {HAZARD[data.hazard[i]] ?? data.hazard[i]} · Tier {data.tier[i]}
      </div>
    </div>
  )
}
