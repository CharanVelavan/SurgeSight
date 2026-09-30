import { useEffect } from 'react'
import { Badge } from '@/components/ui/badge'
import { AppShell } from '@/components/shell/AppShell'
import { trackStore } from '@/data/track'
import { useT } from '@/i18n'
import { useUi } from '@/state/ui'
import { clockActions } from '@/timeline/clock'
import { loadWeather } from '@/weather/atlas'
import { useWeather } from '@/weather/useWeather'
import { MapView } from './MapView'

/** Starts the clock at the newest model run, with the current hour on screen. */
function LiveSync() {
  const manifest = useWeather(s => s.manifest)
  useEffect(() => {
    if (manifest?.live) clockActions.startLive(Date.parse(manifest.live.cycle), Date.parse(manifest.window.end), Date.now())
  }, [manifest])
  return null
}

export function Live() {
  const t = useT()
  useEffect(() => {
    useUi.getState().set({ mode: 'live', field: 'cloud', view: 'india', zones: true, wind: true, rain: true, hoverAsset: null, selectedAsset: null })
    trackStore.setState({ timeline: null, forecast: null })
    void loadWeather('live')
  }, [])
  return (
    <AppShell title={t('tile.live.name')} badge={<Badge className="bg-ok/15 text-ok">{t('header.live')}</Badge>} fill>
      <LiveSync />
      <MapView mode="live" />
    </AppShell>
  )
}
