/** UI preferences that React owns: layer toggles, basemap, rain source and the cursor position. */

import { create } from 'zustand'
import type { RainSource } from '@/weather/field'

export type Basemap = 'dark' | 'satellite' | 'terrain'

interface UiState {
  wind: boolean
  rain: boolean
  rainSource: RainSource
  basemap: Basemap
  /** Last pointer position over the map, or null when the pointer left it. */
  cursor: { lon: number; lat: number; x: number; y: number } | null
  set: (patch: Partial<Omit<UiState, 'set'>>) => void
}

export const useUi = create<UiState>(set => ({
  wind: true,
  rain: true,
  rainSource: 'forecast',
  basemap: 'dark',
  cursor: null,
  set: patch => set(patch),
}))
