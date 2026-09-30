/** Small status labels. Colour is never the only cue: each carries a shape and a word. */

import { ZONE_HEX } from '@/alerts/field'
import { ASSET_ICON } from '@/data/assetIcon'
import type { AssetType } from '@/data/assets'
import { useT, type Key } from '@/i18n'
import { RISK, type RiskClass } from '@/lib/colors'
import { cn } from '@/lib/utils'

export const riskClass = (c: string): RiskClass => (c in RISK ? (c as RiskClass) : 'LOW')

export function RiskBadge({ cls, className }: { cls: string; className?: string }) {
  const t = useT()
  const c = riskClass(cls)
  return (
    <span
      className={cn('inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[12px] font-medium whitespace-nowrap', className)}
      style={{ background: `color-mix(in srgb, ${RISK[c].color} 16%, transparent)`, color: 'var(--foreground)' }}
    >
      <span aria-hidden style={{ color: RISK[c].color }}>{RISK[c].symbol}</span>
      {t(`risk.${c}` as Key)}
    </span>
  )
}

const LEVEL_KEY: Key[] = ['level.none', 'key.watch', 'key.warning', 'key.severe']

export function LevelBadge({ level, className }: { level: number | null | undefined; className?: string }) {
  const t = useT()
  if (level == null) return <span className={cn('text-[12px] text-muted-foreground', className)}>—</span>
  return (
    <span className={cn('inline-flex items-center gap-1.5 text-[12px] font-medium whitespace-nowrap', level === 0 && 'text-muted-foreground', className)}>
      <span
        aria-hidden
        className="inline-block size-2.5 rounded-full"
        style={level === 0 ? { boxShadow: 'inset 0 0 0 1.5px var(--muted-foreground)' } : { background: ZONE_HEX[level] }}
      />
      {t(LEVEL_KEY[level])}
    </span>
  )
}

const ROAD_LEVEL_KEY: Key[] = ['road.level.0', 'road.level.1', 'road.level.2', 'road.level.3']

/** A road section's level as a short line in its map colour and a word. */
export function RoadLevelBadge({ level, className }: { level: number; className?: string }) {
  const t = useT()
  return (
    <span className={cn('inline-flex items-center gap-1.5 text-[12.5px] font-medium whitespace-nowrap', className)}>
      <span aria-hidden className="inline-block h-1 w-4 rounded-full" style={{ background: level ? ZONE_HEX[level] : 'var(--muted-foreground)' }} />
      {t(ROAD_LEVEL_KEY[level] ?? ROAD_LEVEL_KEY[0])}
    </span>
  )
}

const ACCESS_TONE: Record<string, string> = { cut_off: ZONE_HEX[3], at_risk: ZONE_HEX[2] }

/** A facility's screened road access: only shown when it is at risk or cut off. */
export function AccessBadge({ access, className }: { access: string | null | undefined; className?: string }) {
  const t = useT()
  if (access !== 'cut_off' && access !== 'at_risk') return null
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-md border px-1.5 py-0.5 text-[11.5px] font-medium whitespace-nowrap', className)} style={{ borderColor: ACCESS_TONE[access] }}>
      <span aria-hidden className="inline-block size-2 rotate-45" style={{ background: ACCESS_TONE[access] }} />
      {t(`access.${access}` as Key)}
    </span>
  )
}

/** The facility's type icon on a disc in its risk colour, like its map marker. */
export function FacilityIcon({ type, cls, size = 'md' }: { type: string; cls: string; size?: 'sm' | 'md' | 'lg' }) {
  const Icon = ASSET_ICON[type as AssetType]
  const c = riskClass(cls)
  const dark = c === 'LOW' || c === 'MODERATE'
  return (
    <span
      aria-hidden
      className={cn('grid shrink-0 place-items-center rounded-full ring-2 ring-card', size === 'sm' ? 'size-7' : size === 'md' ? 'size-9' : 'size-11')}
      style={{ background: RISK[c].color, color: dark ? '#1B2027' : '#FFFFFF' }}
    >
      {Icon && <Icon className={size === 'sm' ? 'size-3.5' : size === 'md' ? 'size-[18px]' : 'size-5'} strokeWidth={2.2} />}
    </span>
  )
}
