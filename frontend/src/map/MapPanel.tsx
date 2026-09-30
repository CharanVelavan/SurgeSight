/**
 * The map's side panel: each layer is a row with a switch, and when it is on, its key sits right under it.
 * So the panel always answers "what am I seeing?" for exactly what is on the map.
 */

import { CloudRain, Layers3, MapPinned, Palette, Route as RouteIcon, ShieldAlert, Wind } from 'lucide-react'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { ZONE_HEX } from '@/alerts/field'
import { FacilityIcon } from '@/components/badges'
import { ASSET_ICON } from '@/data/assetIcon'
import { ASSET_ORDER, type AssetType } from '@/data/assets'
import { roleById } from '@/data/roles'
import { usePrefs, useResolvedTheme } from '@/app/prefs'
import { t as tt, useT, type Key } from '@/i18n'
import { CLOUD_RAMP_LIGHT, RAIN_RAMP, WIND_RAMP, rampCss, type RiskClass } from '@/lib/colors'
import { formatCycle } from '@/lib/format'
import { cn } from '@/lib/utils'
import { INFRA_ZOOM } from './assetLayers'
import { useUi, type Basemap, type SurfaceField } from '@/state/ui'
import { useClock } from '@/timeline/clock'
import { rainField, windField, type FieldPair, type RainSource } from '@/weather/field'
import { SURFACE } from '@/weather/surface'
import { useWeather } from '@/weather/useWeather'

function sourceLabel(p: FieldPair | null, what: 'wind' | 'rain'): string {
  if (!p) return tt(what === 'wind' ? 'key.noForecast' : 'key.noData')
  if (p.kind === 'forecast') return tt('key.src.forecast', { cycle: formatCycle(Date.parse(p.cycle!)) })
  return tt(`key.src.${p.kind}` as Key)
}

function Scale({ unit, stops, gradient, note, warn }: { unit: string; stops: number[]; gradient: string; note: string; warn?: boolean }) {
  return (
    <div>
      <div className="h-2 rounded-full" style={{ background: gradient }} />
      <div className="num mt-1 flex justify-between text-[11px] text-muted-foreground">
        {stops.map(s => <span key={s}>{s}</span>)}
        <span>{unit}</span>
      </div>
      <p className={cn('mt-1 text-[11.5px]', warn ? 'text-warn' : 'text-muted-foreground')}>{note}</p>
    </div>
  )
}

function Section({ icon: Icon, title, checked, onChange, children, id }: { icon: typeof Wind; title: string; checked?: boolean; onChange?: (v: boolean) => void; children?: React.ReactNode; id: string }) {
  const on = checked ?? true
  return (
    <section className="border-b border-border px-4 py-3.5 last:border-0">
      <div className="flex items-center gap-2.5">
        <Icon className={cn('size-[18px] shrink-0', on ? 'text-primary' : 'text-muted-foreground')} aria-hidden />
        <label htmlFor={`layer-${id}`} className="flex-1 cursor-pointer text-[14px] font-medium">{title}</label>
        {onChange && <Switch id={`layer-${id}`} checked={on} onCheckedChange={onChange} />}
      </div>
      {on && children && <div className="mt-3 pl-7">{children}</div>}
    </section>
  )
}

function ZonesKey() {
  const t = useT()
  return (
    <>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-[12.5px]">
        {(['watch', 'warning', 'severe'] as const).map((k, i) => (
          <span key={k} className="flex items-center gap-1.5">
            <span className="inline-block size-3 rounded-sm border-2" style={{ borderColor: ZONE_HEX[i + 1], background: `${ZONE_HEX[i + 1]}55` }} aria-hidden />
            {t(`key.${k}` as Key)}
          </span>
        ))}
      </div>
      <p className="mt-1.5 text-[11.5px] leading-snug text-muted-foreground">{t('map.zonesNote')}</p>
    </>
  )
}

function TrackKey() {
  const t = useT()
  return (
    <ul className="flex flex-col gap-1.5 text-[12.5px]">
      <li className="flex items-center gap-2.5"><span className="h-[3px] w-6 rounded bg-primary" aria-hidden />{t('map.trackObserved')}</li>
      <li className="flex items-center gap-2.5"><span className="h-0 w-6 border-t-[3px] border-dashed border-[#D99A1E]" aria-hidden />{t('map.trackForecast')}</li>
      <li className="flex items-center gap-2.5"><span className="size-4 rounded-full border border-[#D99A1E] bg-[#D99A1E]/15" aria-hidden />{t('map.trackCircles')}</li>
      <li className="text-[11.5px] leading-snug text-muted-foreground">{t('map.trackNote')}</li>
    </ul>
  )
}

function FacilitiesKey() {
  const t = useT()
  const infra = useUi(s => s.infra)
  const zoom = useUi(s => s.zoom)
  const view = useUi(s => s.view)
  const set = useUi(s => s.set)
  const role = roleById(usePrefs(s => s.role))
  const mine = ASSET_ORDER.every(a => infra[a] === role.types.includes(a))
  return (
    <>
      <div className="mb-2 flex gap-1.5 text-[12px]">
        <button type="button" onClick={() => set({ infra: Object.fromEntries(ASSET_ORDER.map(a => [a, role.types.includes(a)])) as Record<AssetType, boolean> })} className={cn('rounded-md border border-border px-2 py-1', mine && 'border-primary bg-accent text-foreground')}>
          {t('facilities.mine')}
        </button>
        <button type="button" onClick={() => set({ infra: Object.fromEntries(ASSET_ORDER.map(a => [a, true])) as Record<AssetType, boolean> })} className={cn('rounded-md border border-border px-2 py-1', ASSET_ORDER.every(a => infra[a]) && 'border-primary bg-accent text-foreground')}>
          {t('facilities.all')}
        </button>
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        {ASSET_ORDER.map(a => {
          const Icon = ASSET_ICON[a]
          return (
            <button
              key={a}
              type="button"
              aria-pressed={infra[a]}
              onClick={() => set({ infra: { ...infra, [a]: !infra[a] } })}
              className={cn(
                'flex items-center gap-2 rounded-md border px-2 py-1.5 text-left text-[12px] transition-colors',
                infra[a] ? 'border-border bg-card text-foreground' : 'border-dashed border-border text-muted-foreground opacity-70',
              )}
            >
              <Icon className="size-3.5 shrink-0" aria-hidden />
              <span className="truncate">{t(`asset.${a}` as Key)}</span>
            </button>
          )
        })}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-3 gap-y-2 text-[12px]">
        {(['CRITICAL', 'HIGH', 'MODERATE', 'LOW'] as RiskClass[]).map(c => (
          <span key={c} className="flex items-center gap-1.5">
            <FacilityIcon type="hospital" cls={c} size="sm" />
            {t(`risk.${c}` as Key)}
          </span>
        ))}
      </div>
      <p className="mt-2 text-[11.5px] leading-snug text-muted-foreground">{t('map.facilitiesNote')}</p>
      {(zoom < INFRA_ZOOM || view === 'india') && (
        <button type="button" onClick={() => set({ view: 'impact' })} className="mt-2 flex items-center gap-1.5 text-[12.5px] font-medium text-primary hover:underline">
          <MapPinned className="size-3.5" aria-hidden /> {t('map.zoomCoast')}
        </button>
      )}
    </>
  )
}

export function MapPanel() {
  const t = useT()
  const theme = useResolvedTheme()
  const ui = useUi()
  const live = ui.mode === 'live'
  const manifest = useWeather(s => s.manifest)
  const { time, cutoff } = useClock(s => ({ time: Math.floor(s.time / 3_600_000) * 3_600_000, cutoff: s.cutoff }), 300)
  const w = manifest ? windField(manifest, time, cutoff) : null
  const r = manifest ? rainField(manifest, time, cutoff, ui.rainSource) : null
  const set = ui.set
  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-2 px-4 pt-4 pb-1">
        <Layers3 className="size-4 text-muted-foreground" aria-hidden />
        <h2 className="eyebrow">{t('map.layers')}</h2>
      </div>

      <Section id="zones" icon={ShieldAlert} title={t('layers.zones')} checked={ui.zones} onChange={v => set({ zones: v })}>
        <ZonesKey />
      </Section>

      {!live && (
        <Section id="track" icon={RouteIcon} title={t('map.track')} checked={ui.track} onChange={v => set({ track: v })}>
          <TrackKey />
        </Section>
      )}

      {!live && (
        <Section id="facilities" icon={MapPinned} title={t('tab.facilities')}>
          <FacilitiesKey />
        </Section>
      )}

      {live && (
        <Section id="field" icon={Palette} title={t('layers.colourBy')}>
          <ToggleGroup type="single" size="sm" variant="outline" spacing={0} className="w-full" value={ui.field} onValueChange={v => set({ field: (v || 'none') as SurfaceField })} aria-label={t('layers.surface')}>
            {(['none', 'cloud', 'temperature', 'humidity'] as const).map(f => (
              <ToggleGroupItem key={f} value={f} className="flex-1 text-[12px]">{t(`layers.${f}` as Key)}</ToggleGroupItem>
            ))}
          </ToggleGroup>
          {ui.field !== 'none' && manifest && (
            <div className="mt-3">
              <Scale
                unit={SURFACE[ui.field].unit}
                stops={SURFACE[ui.field].stops}
                gradient={rampCss((ui.field === 'cloud' && theme === 'light' ? CLOUD_RAMP_LIGHT : SURFACE[ui.field].ramp).map(([v, h, a]) => [v, h, Math.max(a ?? 1, 0.6)] as const))}
                note={t('key.src.forecast', { cycle: manifest.live ? formatCycle(Date.parse(manifest.live.cycle)) : '' })}
              />
            </div>
          )}
        </Section>
      )}

      <Section id="rain" icon={CloudRain} title={t('layers.rain')} checked={ui.rain} onChange={v => set({ rain: v })}>
        <Scale unit="mm/h" stops={RAIN_RAMP.slice(1).map(([v]) => v)} gradient={rampCss(RAIN_RAMP.slice(1))} note={sourceLabel(r, 'rain')} warn={r?.kind === 'validation' || !r} />
        {!live && (
          <ToggleGroup type="single" size="sm" variant="outline" spacing={0} className="mt-2 w-full" value={ui.rainSource} onValueChange={v => v && set({ rainSource: v as RainSource })} aria-label={t('layers.rainAfter')}>
            <ToggleGroupItem value="forecast" className="flex-1 text-[12px]" title={t('layers.forecastTip')}>{t('layers.forecast')}</ToggleGroupItem>
            <ToggleGroupItem value="observed" className="flex-1 text-[12px]" title={t('layers.observedTip')}>{t('layers.observed')}</ToggleGroupItem>
          </ToggleGroup>
        )}
      </Section>

      <Section id="wind" icon={Wind} title={t('layers.wind')} checked={ui.wind} onChange={v => set({ wind: v })}>
        <Scale unit="m/s" stops={WIND_RAMP.map(([v]) => v)} gradient={rampCss(WIND_RAMP)} note={sourceLabel(w, 'wind')} warn={!w} />
      </Section>

      <section className="px-4 py-3.5">
        <h3 className="mb-2 text-[13px] font-medium">{t('layers.basemap')}</h3>
        <ToggleGroup type="single" size="sm" variant="outline" spacing={0} className="w-full" value={ui.basemap} onValueChange={v => v && set({ basemap: v as Basemap })} aria-label={t('layers.basemap')}>
          {(['dark', 'satellite', 'terrain'] as const).map(b => (
            <ToggleGroupItem key={b} value={b} className="flex-1 text-[12px]">{t(`layers.${b === 'dark' ? 'plain' : b}` as Key)}</ToggleGroupItem>
          ))}
        </ToggleGroup>
      </section>

      <p className="mx-4 mt-1 mb-4 rounded-md bg-muted px-3 py-2 text-[11.5px] leading-snug text-muted-foreground">{t('key.official')}</p>
    </div>
  )
}

