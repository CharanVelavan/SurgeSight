import { useState } from 'react'
import { Layers, X } from 'lucide-react'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { ASSET_ORDER } from '@/data/assets'
import { useT, type Key } from '@/i18n'
import { useUi, type Basemap, type SurfaceField } from '@/state/ui'
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
  const t = useT()
  const { zones, wind, rain, rainSource, basemap, infra, mode, field, set } = useUi()
  const live = mode === 'live'
  // On phones the card is a bottom sheet opened from a button; from 640 px up it floats top-left.
  const [sheet, setSheet] = useState(false)
  return (
    <>
    <button
      type="button"
      onClick={() => setSheet(true)}
      aria-label={t('layers.open')}
      className="panel pointer-events-auto absolute top-16 left-3 z-10 grid size-10 place-items-center sm:hidden"
    >
      <Layers className="size-5" />
    </button>
    <section
      aria-label={t('layers.aria')}
      className={`panel pointer-events-auto absolute top-16 left-3 z-10 w-60 p-3 max-sm:fixed max-sm:inset-x-3 max-sm:top-auto max-sm:bottom-3 max-sm:z-40 max-sm:max-h-[70dvh] max-sm:w-auto max-sm:overflow-y-auto max-sm:pb-[max(0.75rem,env(safe-area-inset-bottom))] ${sheet ? '' : 'max-sm:hidden'}`}
    >
      <button type="button" onClick={() => setSheet(false)} aria-label={t('layers.close')} className="absolute top-2 right-2 grid size-8 place-items-center rounded-lg text-muted-foreground hover:bg-accent sm:hidden">
        <X className="size-4" />
      </button>
      <Heading>{t('layers.weather')}</Heading>
      <Row label={t('layers.zones')} hint={t('layers.zonesHint')} checked={zones} onChange={v => set({ zones: v })} />
      <Row label={t('layers.wind')} hint={t('layers.windHint')} checked={wind} onChange={v => set({ wind: v })} />
      <Row label={t('layers.rain')} hint={t('layers.rainHint')} checked={rain} onChange={v => set({ rain: v })} />
      {live ? (
        <>
          <div className="my-3 h-px bg-[var(--hairline)]" />
          <Heading>{t('layers.colourBy')}</Heading>
          <ToggleGroup type="single" size="sm" variant="outline" spacing={0} className="w-full flex-wrap" value={field} onValueChange={v => set({ field: (v || 'none') as SurfaceField })} aria-label={t('layers.surface')}>
            {(['none', 'cloud', 'temperature', 'humidity'] as const).map(f => (
              <ToggleGroupItem key={f} value={f} className="flex-1 text-[11px] data-[state=on]:bg-accent data-[state=on]:text-foreground">
                {t(`layers.${f === 'none' ? 'none' : f}` as Key)}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </>
      ) : (
        <>
      <ToggleGroup
        type="single"
        size="sm"
        variant="outline"
        spacing={0}
        className="mt-1.5 w-full"
        value={rainSource}
        disabled={!rain}
        onValueChange={v => v && set({ rainSource: v as RainSource })}
        aria-label={t('layers.rainAfter')}
      >
        <ToggleGroupItem value="forecast" className="flex-1 text-[11px] data-[state=on]:bg-accent data-[state=on]:text-foreground" title={t('layers.forecastTip')}>
          {t('layers.forecast')}
        </ToggleGroupItem>
        <ToggleGroupItem value="observed" className="flex-1 text-[11px] data-[state=on]:bg-accent data-[state=on]:text-foreground" title={t('layers.observedTip')}>
          {t('layers.observed')}
        </ToggleGroupItem>
      </ToggleGroup>
        </>
      )}

      {!live && (
        <>
      <div className="my-3 h-px bg-[var(--hairline)]" />
      <Heading>{t('layers.infra')}</Heading>
      <p className="mb-1 text-[11px] text-muted-foreground">{t('layers.infraHint')}</p>
      {ASSET_ORDER.map(a => (
        <Row key={a} label={t(`asset.${a}` as Key)} checked={infra[a]} onChange={v => set({ infra: { ...infra, [a]: v } })} />
      ))}
        </>
      )}

      <div className="my-3 h-px bg-[var(--hairline)]" />
      <Heading>{t('layers.map')}</Heading>
      <ToggleGroup
        type="single"
        size="sm"
        variant="outline"
        spacing={0}
        className="w-full"
        value={basemap}
        onValueChange={v => v && set({ basemap: v as Basemap })}
        aria-label={t('layers.basemap')}
      >
        {(['dark', 'satellite', 'terrain'] as const).map(b => (
          <ToggleGroupItem key={b} value={b} className="flex-1 text-[11px] data-[state=on]:bg-accent data-[state=on]:text-foreground">
            {t(`layers.${b}` as Key)}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </section>
    </>
  )
}
