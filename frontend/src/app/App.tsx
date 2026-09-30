import { useEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { TooltipProvider } from '@/components/ui/tooltip'
import { AppShell, Page } from '@/components/shell/AppShell'
import { Splash } from '@/components/Splash'
import { useT, type Key } from '@/i18n'
import { Guide } from '@/pages/Guide'
import { Home } from '@/pages/Home'
import { Live } from '@/pages/Live'
import { Settings } from '@/pages/Settings'
import { StormWorkspace } from '@/pages/storm/StormWorkspace'
import { Welcome } from '@/pages/Welcome'
import { usePrefs, useApplyTheme } from './prefs'
import { useCatalog } from './queries'
import { Link, navigate, useRoute, type Route } from './router'

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } })

function NotAvailable({ what }: { what: 'live' | 'storm' }) {
  const t = useT()
  return (
    <AppShell title={t(what === 'live' ? 'tile.live.name' : 'nav.storms')}>
      <Page className="max-w-xl text-center">
        <p className="mt-16 text-[18px] font-semibold">{what === 'live' ? t('app.unavailableLive') : t('app.unavailableStorm')}</p>
        <Button asChild variant="outline" className="mt-5"><Link to="/">{t('app.back')}</Link></Button>
      </Page>
    </AppShell>
  )
}

/** Opens a view only when the catalog says its data is ready; while it checks, the loading page shows. */
function Gate({ route }: { route: Extract<Route, { name: 'live' | 'storm' }> }) {
  const t = useT()
  const { data, isError } = useCatalog()
  const id = route.name === 'live' ? 'live' : route.id
  const kind = route.name
  if (isError && kind === 'storm') return <StormWorkspace id={route.id} tab={route.tab} />
  if (!data && !isError) return <Splash label={t('splash.opening', { name: t(`tile.${id}.name` as Key) })} />
  if (!data?.tiles.some(tile => tile.id === id && tile.kind === kind && tile.status === 'available')) return <NotAvailable what={kind} />
  return route.name === 'live' ? <Live /> : <StormWorkspace id={route.id} tab={route.tab} />
}

function Screens() {
  useApplyTheme()
  const route = useRoute()
  const onboarded = usePrefs(s => s.onboarded)
  const needsWelcome = !onboarded && route.name !== 'welcome'
  useEffect(() => {
    if (needsWelcome && location.pathname !== '/welcome') navigate(`/welcome?next=${encodeURIComponent(location.pathname)}`, true)
  }, [needsWelcome])
  useEffect(() => {
    if (route.name !== 'storm' || route.tab !== 'map') document.getElementById('main')?.scrollTo(0, 0)
  }, [route])
  if (needsWelcome) return null
  switch (route.name) {
    case 'welcome':
      return <Welcome />
    case 'home':
      return <Home />
    case 'guide':
      return <Guide />
    case 'settings':
      return <Settings />
    case 'live':
    case 'storm':
      return <Gate route={route} />
  }
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={300}>
        <Screens />
      </TooltipProvider>
    </QueryClientProvider>
  )
}
