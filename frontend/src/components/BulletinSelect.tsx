import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useTimeline } from '@/app/queries'
import { useT } from '@/i18n'
import { formatIST } from '@/lib/format'
import { clockActions, useClock } from '@/timeline/clock'

/** Choose which bulletin to look at: every screen then shows only what was known at that time. */
export function BulletinSelect({ className = '' }: { className?: string }) {
  const t = useT()
  const { data: tl } = useTimeline()
  const cutoff = useClock(s => s.cutoff, 200)
  if (!tl) return null
  const options = tl.cutoffs.map(c => Date.parse(c))
  if (!options.includes(cutoff)) options.push(cutoff)
  options.sort((a, b) => a - b)
  return (
    <Select
      value={String(cutoff)}
      onValueChange={v => {
        const ms = Number(v)
        clockActions.setCutoff(ms)
        clockActions.setTime(ms)
      }}
    >
      <SelectTrigger aria-label={t('overview.bulletin')} className={`num min-w-52 ${className}`}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map(ms => (
          <SelectItem key={ms} value={String(ms)} className="num">
            {formatIST(ms)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
