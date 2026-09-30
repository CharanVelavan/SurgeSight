import { AlertTriangle } from 'lucide-react'
import { formatCycle } from '@/lib/format'
import { useWeather } from '@/weather/useWeather'

/** Which model run the live view shows, how old it is, and a warning when it is too old to rely on. */
export function LiveBanner() {
  const live = useWeather(s => s.manifest?.live)
  if (!live) return null
  const age = Math.round(live.age_hours)
  return (
    <div
      role="status"
      className={`panel pointer-events-auto absolute top-16 left-1/2 z-20 flex max-w-[calc(100%-1.5rem)] -translate-x-1/2 items-center gap-2 px-3 py-1.5 text-[12px] ${live.stale ? 'text-[#E0B34A]' : 'text-muted-foreground'}`}
    >
      {live.stale && <AlertTriangle className="size-4 shrink-0" aria-hidden />}
      <span>
        {live.stale ? (
          <>
            This forecast is {age} h old (older than {live.stale_after_hours} h). Do not use it for current conditions; check IMD.
          </>
        ) : (
          <>
            NOAA GFS model run {formatCycle(Date.parse(live.cycle))} · {age} h old · forecast, not observation
          </>
        )}
      </span>
    </div>
  )
}
