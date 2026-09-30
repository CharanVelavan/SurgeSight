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
import { AssetWhy } from '@/panels/AssetWhy'
import { Intro } from '@/panels/Intro'
import { Landing } from './Landing'
import { LiveBanner } from '@/panels/LiveBanner'
import { clockActions } from '@/timeline/clock'
import { trackStore } from '@/data/track'
import { useUi } from '@/state/ui'
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

function LiveSync() {
  const manifest = useWeather(s => s.manifest)
  useEffect(() => {
    if (manifest?.live) clockActions.startLive(Date.parse(manifest.live.cycle), Date.parse(manifest.window.end), Date.now())
  }, [manifest])
  return null
}

function Dashboard({ mode }: { mode: 'replay' | 'live' }) {
  useEffect(() => {
    useUi.getState().set({ mode, field: mode === 'live' ? 'cloud' : 'none', view: 'india', hoverAsset: null, selectedAsset: null })
    if (mode === 'live') trackStore.setState({ timeline: null, forecast: null })
    else clockActions.resetReplay()
    void loadWeather(mode)
    if (mode === 'replay') void loadAssets()
  }, [mode])
  return (
    <TooltipProvider delayDuration={300}>
      <main className="relative h-full w-full overflow-hidden bg-background">
        {mode === 'replay' ? <TrackSync /> : <LiveSync />}
        <MapCanvas />
        <TopBar />
        {mode === 'live' && <LiveBanner />}
        {mode === 'replay' && <ViewSwitch />}
        {mode === 'replay' && <AtRisk />}
        <LayerCard />
        <Legend />
        <Timeline />
        <CursorReadout />
        <AssetPopover />
        <AssetWhy />
        <LoadingNote />
        <Intro />
        {showPerf && <PerfOverlay />}
      </main>
    </TooltipProvider>
  )
}

function NotAvailable({ what }: { what: string }) {
  return (
    <main className="grid h-full place-items-center bg-background px-6 text-center">
      <div>
        <p className="text-lg font-semibold">{what} is not available yet</p>
        <a href="/" onClick={e => onLinkClick(e, '/')} className="mt-3 inline-block text-sm text-primary underline">Back to all views</a>
      </div>
    </main>
  )
}

/** Opens a view only when the catalog says its data is ready; anything else says so and links back. */
function Gate({ id, kind }: { id: string; kind: 'live' | 'storm' }) {
  const { data, isError } = useQuery({ queryKey: ['catalog'], queryFn: api.catalog, staleTime: 60_000 })
  const mode = kind === 'live' ? 'live' : 'replay'
  if (isError && kind === 'storm') return <Dashboard mode="replay" />
  if (!data && !isError) return <main className="grid h-full place-items-center bg-background text-sm text-muted-foreground">Loading…</main>
  if (!data?.tiles.some(t => t.id === id && t.kind === kind && t.status === 'available')) return <NotAvailable what={kind === 'live' ? 'Live weather' : 'This storm'} />
  return <Dashboard mode={mode} />
}

export default function App() {
  const route = useRoute()
  return (
    <QueryClientProvider client={queryClient}>
      {route.name === 'landing' && <Landing />}
      {route.name === 'live' && <Gate id="live" kind="live" />}
      {route.name === 'storm' && <Gate id={route.id} kind="storm" />}
    </QueryClientProvider>
  )
}
