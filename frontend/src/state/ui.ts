/** UI preferences that React owns: layer toggles, basemap, rain source and the cursor position. */

import { create } from 'zustand'
import type { AssetType } from '@/data/assets'
import type { RainSource } from '@/weather/field'

export type Basemap = 'dark' | 'satellite' | 'terrain'
export type View = 'india' | 'impact'
export type Mode = 'replay' | 'live'
export type SurfaceField = 'none' | 'cloud' | 'temperature' | 'humidity'

const infraDefault: Record<AssetType, boolean> = {
  hospital: true, substation: true, police_station: true, fire_station: true, shelter: true,
  school: false, water_facility: true, fishing_harbour: true,
}

interface UiState {
  /** 'replay' is a past storm; 'live' is the newest weather forecast over India. */
  mode: Mode
  /** Extra weather colour layer, live mode only. */
  field: SurfaceField
  wind: boolean
  zones: boolean
  track: boolean
  surge: boolean
  /** Main roads screened for flooding and fallen trees (storm replays only). */
  roads: boolean
  rain: boolean
  rainSource: RainSource
  basemap: Basemap
  /** 'india' is the locked national frame; 'impact' zooms to the affected coast. */
  view: View
  zoom: number
  infra: Record<AssetType, boolean>
  /** Index into the columnar asset arrays of the marker under the pointer. */
  hoverAsset: number | null
  /** Index of the marker the user clicked; opens the details panel. */
  selectedAsset: number | null
  /** Index of the road section the user clicked; opens the road panel. */
  selectedRoad: number | null
  /** True while the opening fly-in plays. */
  intro: boolean
  /** One-shot request to fly the camera to a point (used by the summary list). */
  focus: { lon: number; lat: number; zoom: number } | null
  /** Last pointer position over the map, or null when the pointer left it. */
  cursor: { lon: number; lat: number; x: number; y: number } | null
  set: (patch: Partial<Omit<UiState, 'set'>>) => void
}

export const useUi = create<UiState>(set => ({
  mode: 'replay',
  field: 'none',
  wind: true,
  zones: true,
  track: true,
  surge: true,
  roads: true,
  rain: true,
  rainSource: 'forecast',
  basemap: 'dark',
  view: 'india',
  zoom: 4,
  infra: infraDefault,
  hoverAsset: null,
  selectedAsset: null,
  selectedRoad: null,
  intro: false,
  focus: null,
  cursor: null,
  set: patch => set(patch),
}))
