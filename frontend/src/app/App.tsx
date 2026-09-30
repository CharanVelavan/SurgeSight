import { useEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TooltipProvider } from '@/components/ui/tooltip'
import { TrackSync } from './TrackSync'
import { MapCanvas } from '@/map/MapCanvas'
import { CursorReadout } from '@/panels/CursorReadout'
import { LayerCard } from '@/panels/LayerCard'
import { Legend } from '@/panels/Legend'
import { PerfOverlay } from '@/panels/PerfOverlay'
import { TopBar } from '@/panels/TopBar'
import { Timeline } from '@/timeline/Timeline'
import { loadAssets } from '@/data/assets'
import { AtRisk } from '@/panels/AtRisk'
import { AssetPopover } from '@/panels/AssetPopover'
import { Intro } from '@/panels/Intro'
import { ViewSwitch } from '@/panels/ViewSwitch'
import { loadWeather } from '@/weather/atlas'
import { useWeather } from '@/weather/useWeather'

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } })
const showPerf = new URLSearchParams(location.search).has('perf')

function LoadingNote() {
  const loaded = useWeather(s => s.loaded)
  const total = useWeather(s => s.total)
  const error = useWeather(s => s.error)
  if (error) return <div className="panel absolute top-16 left-1/2 z-30 -translate-x-1/2 px-3 py-1.5 text-xs text-[#E0B34A]">Weather frames unavailable: {error}</div>
  if (!total || loaded >= total) return null
  return (
    <div className="panel num absolute top-16 left-1/2 z-30 -translate-x-1/2 px-3 py-1.5 text-xs text-muted-foreground">
      Loading weather {loaded}/{total}
    </div>
  )
}

export default function App() {
  useEffect(() => {
    void loadWeather()
    void loadAssets()
  }, [])
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={300}>
        <main className="relative h-full w-full overflow-hidden bg-background">
          <TrackSync />
          <MapCanvas />
          <TopBar />
          <ViewSwitch />
          <AtRisk />
          <LayerCard />
          <Legend />
          <Timeline />
          <CursorReadout />
          <AssetPopover />
          <LoadingNote />
          <Intro />
          {showPerf && <PerfOverlay />}
        </main>
      </TooltipProvider>
    </QueryClientProvider>
  )
}
