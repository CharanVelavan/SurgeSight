import { useState } from 'react'
import { SlidersHorizontal } from 'lucide-react'
import { useStore } from 'zustand'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { Splash } from '@/components/Splash'
import { assetsStore } from '@/data/assets'
import { useMediaQuery } from '@/lib/useMediaQuery'
import { useT } from '@/i18n'
import { MapCanvas } from '@/map/MapCanvas'
import { MapPanel } from '@/map/MapPanel'
import { AssetPopover } from '@/panels/AssetPopover'
import { CursorReadout } from '@/panels/CursorReadout'
import { FacilityDetails } from '@/panels/FacilityDetails'
import { LiveBanner } from '@/panels/LiveBanner'
import { PerfOverlay } from '@/panels/PerfOverlay'
import { ViewSwitch } from '@/panels/ViewSwitch'
import { useUi } from '@/state/ui'
import { Timeline } from '@/timeline/Timeline'
import { useWeather } from '@/weather/useWeather'

const showPerf = new URLSearchParams(location.search).has('perf')

function WeatherLoading() {
  const t = useT()
  const loaded = useWeather(s => s.loaded)
  const total = useWeather(s => s.total)
  const error = useWeather(s => s.error)
  if (error)
    return (
      <div role="alert" className="panel absolute top-3 left-1/2 z-30 -translate-x-1/2 px-3 py-2 text-[13px] text-warn">
        {t('app.weatherError', { error })}
      </div>
    )
  if (total && loaded >= total) return null
  return <Splash overlay label={t('map.loading')} progress={total ? loaded / total : null} />
}

/**
 * The map screen for a storm or the live weather: a full-bleed map with translucent panels floating over it,
 * the layers and their key on the right and the timeline along the bottom. On phones the panel and the facility details open as sheets.
 */
export function MapView({ mode }: { mode: 'replay' | 'live' }) {
  const t = useT()
  const wide = useMediaQuery('(min-width: 1024px)')
  const selected = useUi(s => s.selectedAsset)
  const set = useUi(s => s.set)
  const hasAssets = useStore(assetsStore, s => !!s.data)
  const [panel, setPanel] = useState(false)
  const details = selected !== null && hasAssets && mode === 'replay'
  const close = () => set({ selectedAsset: null })
  return (
    <div className="relative h-full overflow-hidden" data-map-root>
      <MapCanvas />
      {mode === 'replay' && <ViewSwitch />}
      {mode === 'live' && <LiveBanner />}
      {!wide && (
        <Button variant="outline" size="sm" onClick={() => setPanel(true)} className="panel absolute top-3 right-3 z-10 h-9 gap-1.5 text-[13px]">
          <SlidersHorizontal className="size-4" /> {t('map.layers')}
        </Button>
      )}
      <WeatherLoading />
      {showPerf && <PerfOverlay />}
      <Timeline className={wide ? 'bottom-8 left-3 right-[calc(340px+1.5rem)]' : 'inset-x-2 bottom-7'} />

      {wide && (
        <aside
          aria-label={details ? t('why.aria') : t('map.layers')}
          className="panel pointer-events-auto absolute top-3 right-3 bottom-8 z-20 w-[340px] overflow-y-auto"
        >
          {details ? (
            <div className="p-4">
              <FacilityDetails index={selected} onClose={close} />
            </div>
          ) : (
            <MapPanel />
          )}
        </aside>
      )}
      {!wide && (
        <>
          <Sheet open={panel} onOpenChange={setPanel}>
            <SheetContent side="bottom" className="max-h-[80dvh] overflow-y-auto rounded-t-xl p-0" aria-describedby={undefined}>
              <SheetTitle className="sr-only">{t('map.layers')}</SheetTitle>
              <MapPanel />
            </SheetContent>
          </Sheet>
          <Sheet open={details} onOpenChange={o => !o && close()}>
            <SheetContent side="bottom" className="max-h-[85dvh] overflow-y-auto rounded-t-xl p-4" showCloseButton={false} aria-describedby={undefined}>
              <SheetTitle className="sr-only">{t('why.aria')}</SheetTitle>
              {details && <FacilityDetails index={selected} onClose={close} />}
            </SheetContent>
          </Sheet>
        </>
      )}
      <CursorReadout />
      <AssetPopover />
    </div>
  )
}
