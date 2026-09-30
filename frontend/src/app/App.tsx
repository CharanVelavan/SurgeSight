import { useEffect } from 'react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { TooltipProvider } from '@/components/ui/tooltip'
import { TrackSync } from './TrackSync'
import { MapCanvas } from '@/map/MapCanvas'
import { CursorReadout } from '@/panels/CursorReadout'
import { LayerCard } from '@/panels/LayerCard'
import { Legend } from '@/panels/Legend'
import { PerfOverlay } from '@/panels/PerfOverlay'
import { TopBar } from '@/panels/TopBar'
import { Timeline } from '@/timeline/Timeline'
import { api } from '@/lib/api'
import { loadAssets } from '@/data/assets'
import { AtRisk } from '@/panels/AtRisk'
import { AssetPopover } from '@/panels/AssetPopover'
import { Intro } from '@/panels/Intro'
import { Landing } from './Landing'
import { onLinkClick, useRoute } from './router'
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

function Dashboard() {
  useEffect(() => {
    void loadWeather()
    void loadAssets()
  }, [])
  return (
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
  )
}

function LiveSoon() {
  return (
    <main className="grid h-full place-items-center bg-background px-6 text-center">
      <div>
        <p className="text-lg font-semibold">Live weather is not connected yet</p>
        <a href="/" onClick={e => onLinkClick(e, '/')} className="mt-3 inline-block text-sm text-primary underline">Back to all views</a>
      </div>
    </main>
  )
}

/** Opens a storm only when the catalog says its data is ready; anything else goes back to the list. */
function StormGate({ id }: { id: string }) {
  const { data, isError } = useQuery({ queryKey: ['catalog'], queryFn: api.catalog, staleTime: 60_000 })
  if (isError) return <Dashboard />
  if (!data) return <main className="grid h-full place-items-center bg-background text-sm text-muted-foreground">Loading…</main>
  if (!data.tiles.some(t => t.id === id && t.kind === 'storm' && t.status === 'available'))
    return (
      <main className="grid h-full place-items-center bg-background px-6 text-center">
        <div>
          <p className="text-lg font-semibold">This storm is not available yet</p>
          <a href="/" onClick={e => onLinkClick(e, '/')} className="mt-3 inline-block text-sm text-primary underline">Back to all views</a>
        </div>
      </main>
    )
  return <Dashboard />
}

export default function App() {
  const route = useRoute()
  return (
    <QueryClientProvider client={queryClient}>
      {route.name === 'landing' && <Landing />}
      {route.name === 'live' && <LiveSoon />}
      {route.name === 'storm' && <StormGate id={route.id} />}
    </QueryClientProvider>
  )
}
