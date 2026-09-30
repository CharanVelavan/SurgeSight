import { Logo } from './shell/Logo'

/** Loading page: the mark, what is loading and, when known, how far along it is. */
export function Splash({ label, progress, overlay = false }: { label: string; progress?: number | null; overlay?: boolean }) {
  const pct = progress == null ? null : Math.round(Math.min(1, Math.max(0, progress)) * 100)
  return (
    <div
      role="status"
      aria-live="polite"
      className={`grid place-items-center bg-background ${overlay ? 'absolute inset-0 z-30 bg-background/80 backdrop-blur-sm' : 'h-full'}`}
    >
      <div className="flex w-64 flex-col items-center text-center">
        <Logo className="size-11 motion-safe:animate-pulse" />
        <div className="mt-4 text-[15px] font-semibold tracking-tight">SurgeSight</div>
        <div className="mt-1 text-[13px] text-muted-foreground">{label}</div>
        <div className="mt-4 h-1 w-full overflow-hidden rounded-full bg-muted" aria-hidden>
          {pct === null ? (
            <div className="h-full w-1/3 rounded-full bg-primary motion-safe:animate-[splash_1.2s_ease-in-out_infinite]" />
          ) : (
            <div className="h-full rounded-full bg-primary transition-[width] duration-300" style={{ width: `${pct}%` }} />
          )}
        </div>
        {pct !== null && <div className="num mt-1.5 text-[11px] text-muted-foreground">{pct}%</div>}
      </div>
    </div>
  )
}
