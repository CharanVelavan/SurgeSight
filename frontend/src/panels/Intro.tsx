import { useUi } from '@/state/ui'

/** Title over the opening fly-in. Any click or key press skips the flight (handled by the map controller). */
export function Intro() {
  const intro = useUi(s => s.intro)
  return (
    <div
      className="pointer-events-none absolute inset-0 z-30 grid place-items-center bg-background/35 transition-opacity duration-700"
      style={{ opacity: intro ? 1 : 0 }}
      aria-hidden={!intro}
    >
      <div className="text-center">
        <div className="text-3xl font-semibold tracking-tight">SurgeSight</div>
        <div className="mt-1.5 text-sm text-muted-foreground">Cyclone Michaung · 30 Nov – 6 Dec 2023</div>
        <div className="mt-6 text-[11px] tracking-[0.14em] text-muted-foreground/70 uppercase">Click or press any key to skip</div>
      </div>
    </div>
  )
}
