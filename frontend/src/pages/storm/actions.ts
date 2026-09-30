import { navigate, pathFor } from '@/app/router'
import { assetsStore } from '@/data/assets'
import { useUi } from '@/state/ui'

/** Open the storm's map zoomed to one facility, with its details shown. */
export function showOnMap(stormId: string, index: number): void {
  const data = assetsStore.getState().data
  if (!data) return
  useUi.getState().set({ view: 'impact', selectedAsset: index, infra: { ...useUi.getState().infra, [data.type[index]]: true } })
  navigate(pathFor({ name: 'storm', id: stormId, tab: 'map' }))
  setTimeout(() => useUi.getState().set({ focus: { lon: data.lon[index], lat: data.lat[index], zoom: 12.5 } }), 60)
}
