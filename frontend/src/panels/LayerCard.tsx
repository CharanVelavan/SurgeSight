import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useUi, type Basemap } from '@/state/ui'
import type { RainSource } from '@/weather/field'

function Row({ label, hint, checked, onChange }: { label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void }) {
  const id = `layer-${label.toLowerCase()}`
  return (
    <label htmlFor={id} className="flex cursor-pointer items-center justify-between gap-6 py-1">
      <span className="text-[13px]">
        {label}
        {hint && <span className="ml-1.5 text-[11px] text-muted-foreground">{hint}</span>}
      </span>
      <Switch id={id} size="sm" checked={checked} onCheckedChange={onChange} />
    </label>
  )
}

const Heading = ({ children }: { children: string }) => (
  <div className="mb-1 text-[10px] font-medium tracking-[0.14em] text-muted-foreground uppercase">{children}</div>
)

export function LayerCard() {
  const { wind, rain, rainSource, basemap, set } = useUi()
  return (
    <section aria-label="Layers" className="panel pointer-events-auto absolute top-16 left-3 z-10 w-60 p-3 max-sm:hidden">
      <Heading>Weather</Heading>
      <Row label="Wind" hint="10 m" checked={wind} onChange={v => set({ wind: v })} />
      <Row label="Rain" hint="mm/h" checked={rain} onChange={v => set({ rain: v })} />
      <ToggleGroup
        type="single"
        size="sm"
        variant="outline"
        spacing={0}
        className="mt-1.5 w-full"
        value={rainSource}
        disabled={!rain}
        onValueChange={v => v && set({ rainSource: v as RainSource })}
        aria-label="Rain after the cutoff"
      >
        <ToggleGroupItem value="forecast" className="flex-1 text-[11px] data-[state=on]:bg-accent data-[state=on]:text-foreground" title="GFS forecast as issued at the cutoff (no hindsight)">
          Forecast
        </ToggleGroupItem>
        <ToggleGroupItem value="observed" className="flex-1 text-[11px] data-[state=on]:bg-accent data-[state=on]:text-foreground" title="IMERG satellite rain after the cutoff: validation only, not knowable at the cutoff">
          Observed · validation
        </ToggleGroupItem>
      </ToggleGroup>

      <div className="my-3 h-px bg-[var(--hairline)]" />
      <Heading>Map</Heading>
      <ToggleGroup
        type="single"
        size="sm"
        variant="outline"
        spacing={0}
        className="w-full"
        value={basemap}
        onValueChange={v => v && set({ basemap: v as Basemap })}
        aria-label="Basemap"
      >
        {(['dark', 'satellite', 'terrain'] as const).map(b => (
          <ToggleGroupItem key={b} value={b} className="flex-1 text-[11px] capitalize data-[state=on]:bg-accent data-[state=on]:text-foreground">
            {b}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </section>
  )
}
