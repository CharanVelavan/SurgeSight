import { useTimeline } from '@/app/queries'
import { imdClass, trackAt } from '@/lib/imd'
import { formatIST } from '@/lib/format'
import { useClock } from '@/timeline/clock'

export function TopBar() {
  const { data: timeline } = useTimeline()
  const time = useClock(s => s.time, 250)
  const point = timeline ? trackAt(timeline.track, time) : null
  const cls = point ? imdClass(point.wind_kt) : null

  return (
    <header className="pointer-events-none absolute inset-x-0 top-0 z-20 flex h-12 items-center gap-3 px-3 pt-[env(safe-area-inset-top)]">
      <div className="panel pointer-events-auto flex h-9 items-center gap-2 px-3">
        <svg viewBox="0 0 32 32" className="size-5" aria-hidden>
          <path d="M6 19c4-6 8-6 10-2s6 4 10-2" fill="none" stroke="var(--primary)" strokeWidth="2.5" strokeLinecap="round" />
          <path d="M6 24c4-4 8-4 10-1s6 3 10-1" fill="none" stroke="var(--primary)" strokeOpacity=".5" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <span className="text-sm font-semibold tracking-tight">SurgeSight</span>
      </div>

      <div className="panel pointer-events-auto flex h-9 min-w-0 items-center gap-2.5 px-3 text-[13px]">
        <span className="font-semibold tracking-wide">{timeline?.cyclone ?? '…'}</span>
        {cls ? (
          <span className="truncate text-muted-foreground max-sm:hidden" title={`${point!.wind_kt.toFixed(0)} kt · ${point!.pressure_hpa.toFixed(0)} hPa (observed best track)`}>
            {cls.long}
          </span>
        ) : (
          <span className="text-muted-foreground max-sm:hidden">outside observed track</span>
        )}
        <span className="num text-foreground/90">{formatIST(time)}</span>
      </div>

      <div className="ml-auto flex items-center gap-2">
        <span className="panel pointer-events-auto flex h-9 items-center gap-1.5 px-3 text-[11px] font-medium tracking-[0.12em] text-muted-foreground">
          <span className="size-1.5 rounded-full bg-muted-foreground" aria-hidden />
          REPLAY
        </span>
      </div>
    </header>
  )
}
