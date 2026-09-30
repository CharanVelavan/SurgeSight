import { useEffect } from 'react'
import { Badge } from '@/components/ui/badge'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { AppShell } from '@/components/shell/AppShell'
import { TrackSync } from '@/app/TrackSync'
import { usePrefs } from '@/app/prefs'
import type { StormTab } from '@/app/router'
import { ASSET_ORDER, loadAssets, type AssetType } from '@/data/assets'
import { roleById } from '@/data/roles'
import { loadSurge } from '@/data/surge'
import { useT, type Key } from '@/i18n'
import { FacilityDetails } from '@/panels/FacilityDetails'
import { useUi } from '@/state/ui'
import { clockActions } from '@/timeline/clock'
import { loadWeather } from '@/weather/atlas'
import { MapView } from '../MapView'
import { showOnMap } from './actions'
import { Advisories } from './Advisories'
import { Areas } from './Areas'
import { Facilities } from './Facilities'
import { Overview } from './Overview'

/** Facility details over the list pages (the map shows them in its own side panel). */
function FacilitySheet({ id }: { id: string }) {
  const t = useT()
  const selected = useUi(s => s.selectedAsset)
  const set = useUi(s => s.set)
  const close = () => set({ selectedAsset: null })
  return (
    <Sheet open={selected !== null} onOpenChange={o => !o && close()}>
      <SheetContent side="right" className="w-full overflow-y-auto p-5 sm:max-w-md" showCloseButton={false} aria-describedby={undefined}>
        <SheetTitle className="sr-only">{t('why.aria')}</SheetTitle>
        {selected !== null && <FacilityDetails index={selected} onClose={close} onShowOnMap={() => showOnMap(id, selected)} />}
      </SheetContent>
    </Sheet>
  )
}

/** One storm: its data loads once here and stays while the user moves between Overview, Map, Facilities and Areas. */
export function StormWorkspace({ id, tab }: { id: string; tab: StormTab }) {
  const t = useT()
  useEffect(() => {
    const prefs = usePrefs.getState()
    const role = roleById(prefs.role)
    useUi.getState().set({
      mode: 'replay', field: 'none', view: 'india', zones: true, track: true, surge: true, wind: prefs.stormWind, rain: prefs.stormRain,
      rainSource: 'forecast', hoverAsset: null, selectedAsset: null,
      infra: Object.fromEntries(ASSET_ORDER.map(a => [a, role.types.includes(a)])) as Record<AssetType, boolean>,
    })
    clockActions.resetReplay()
    void loadWeather('replay')
    void loadAssets()
    void loadSurge()
  }, [id])
  // A facility opened on one tab should not pop up over the next one (the map keeps it: it shows it inline).
  useEffect(() => {
    if (tab !== 'map') useUi.getState().set({ selectedAsset: null })
  }, [tab])
  return (
    <AppShell title={t(`tile.${id}.name` as Key)} badge={<Badge variant="secondary">{t('tile.replay')}</Badge>} fill={tab === 'map'}>
      <TrackSync />
      {tab === 'overview' && <Overview id={id} />}
      {tab === 'map' && <MapView mode="replay" />}
      {tab === 'facilities' && <Facilities id={id} />}
      {tab === 'areas' && <Areas />}
      {tab === 'advisories' && <Advisories />}
      {tab !== 'map' && <FacilitySheet id={id} />}
    </AppShell>
  )
}
