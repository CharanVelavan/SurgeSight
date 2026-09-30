/** UI preferences that React owns: layer toggles, basemap, rain source and the cursor position. */

import { create } from 'zustand'
import type { AssetType } from '@/data/assets'
import type { RainSource } from '@/weather/field'

export type Basemap = 'dark' | 'satellite' | 'terrain'
export type View = 'india' | 'impact'

const infraDefault: Record<AssetType, boolean> = {
  hospital: true, substation: true, police_station: true, fire_station: true, shelter: true,
  school: false, water_facility: true, fishing_harbour: true,
}

interface UiState {
  wind: boolean
  rain: boolean
  rainSource: RainSource
  basemap: Basemap
  /** 'india' is the locked national frame; 'impact' zooms to the affected coast. */
  view: View
  zoom: number
  infra: Record<AssetType, boolean>
  /** Index into the columnar asset arrays of the marker under the pointer. */
  hoverAsset: number | null
  /** True while the opening fly-in plays. */
  intro: boolean
  /** One-shot request to fly the camera to a point (used by the summary list). */
  focus: { lon: number; lat: number; zoom: number } | null
  /** Last pointer position over the map, or null when the pointer left it. */
  cursor: { lon: number; lat: number; x: number; y: number } | null
  set: (patch: Partial<Omit<UiState, 'set'>>) => void
}

export const useUi = create<UiState>(set => ({
  wind: true,
  rain: true,
  rainSource: 'forecast',
  basemap: 'dark',
  view: 'india',
  zoom: 4,
  infra: infraDefault,
  hoverAsset: null,
  intro: false,
  focus: null,
  cursor: null,
  set: patch => set(patch),
}))
