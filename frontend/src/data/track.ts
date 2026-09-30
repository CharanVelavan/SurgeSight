/** Storm track and experimental forecast, mirrored from React Query into a vanilla store for the frame loop. */

import { createStore } from 'zustand/vanilla'
import type { ExperimentalForecast, Timeline } from '@/lib/api'

interface TrackState {
  timeline: Timeline | null
  forecast: ExperimentalForecast['data'] | null
}

export const trackStore = createStore<TrackState>(() => ({ timeline: null, forecast: null }))
