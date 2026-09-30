import { AlertTriangle } from 'lucide-react'
import { useT } from '@/i18n'
import { formatCycle } from '@/lib/format'
import { useWeather } from '@/weather/useWeather'

/** Which model run the live view shows, how old it is, and a warning when it is too old to rely on. */
export function LiveBanner() {
  const t = useT()
  const live = useWeather(s => s.manifest?.live)
  if (!live) return null
  const age = Math.round(live.age_hours)
  return (
    <div
      role="status"
      className={`panel pointer-events-auto absolute top-3 left-1/2 z-20 flex max-w-[calc(100%-1.5rem)] max-lg:top-14 -translate-x-1/2 items-center gap-2 px-3 py-2 text-[12.5px] ${live.stale ? 'border-warn/40 text-warn' : 'text-muted-foreground'}`}
    >
      {live.stale && <AlertTriangle className="size-4 shrink-0" aria-hidden />}
      <span>
        {live.stale
          ? t('live.stale', { age, limit: live.stale_after_hours })
          : t('live.fresh', { cycle: formatCycle(Date.parse(live.cycle)), age })}
      </span>
    </div>
  )
}
