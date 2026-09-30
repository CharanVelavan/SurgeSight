/** The live surface fields: what they are called, how they are stored in the extra atlas and how they read out. */

import { CLOUD_RAMP, HUMIDITY_RAMP, TEMP_RAMP, type Stop } from '@/lib/colors'
import type { SurfaceField } from '@/state/ui'

export const SURFACE: Record<Exclude<SurfaceField, 'none'>, { label: string; unit: string; channel: 0 | 1 | 2; min: number; max: number; ramp: readonly Stop[]; stops: number[]; digits: number }> = {
  cloud: { label: 'Cloud cover', unit: '%', channel: 0, min: 0, max: 100, ramp: CLOUD_RAMP, stops: [15, 40, 70, 100], digits: 0 },
  temperature: { label: 'Temperature', unit: '°C', channel: 1, min: -30, max: 50, ramp: TEMP_RAMP, stops: [-10, 5, 18, 28, 36, 44], digits: 0 },
  humidity: { label: 'Humidity', unit: '%', channel: 2, min: 0, max: 100, ramp: HUMIDITY_RAMP, stops: [20, 50, 80, 100], digits: 0 },
}
