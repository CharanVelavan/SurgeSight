/** Typed client for the FastAPI routes the command UI uses. */

export interface TrackPoint { time: string; lat: number; lon: number; wind_kt: number; pressure_hpa: number }

export interface Timeline {
  region: string
  cyclone: string
  timezone: 'UTC'
  demo_cutoff: string
  start: string
  end: string
  track: TrackPoint[]
  cutoffs: string[]
  first_over_land: { time: string; lat: number; lon: number; note: string } | null
}

export interface AssetColumns {
  count: number
  run_id: string | null
  lon: number[]
  lat: number[]
  name: string[]
  asset_type: string[]
  risk_class: string[]
  risk_score: number[]
  triage_tier: number[]
  dominant_hazard: string[]
}

export interface ForecastPoint {
  lead_hours: number
  timestamp: string
  lat: number
  lon: number
  uncertainty_radius_km: number
}

export interface ForecastModel { label: string; forecast: ForecastPoint[] }

export interface ExperimentalForecast {
  run_id: string
  data: {
    forecast_label: string
    disclaimer: string
    cutoff_time: string
    last_observation_time: string
    models: Record<'position_only_kalman' | 'wind_informed_kalman', ForecastModel>
  }
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`)
  return (await res.json()) as T
}

export const api = {
  timeline: () => get<Timeline>('/api/timeline'),
  forecast: (cutoff: string) => get<ExperimentalForecast>(`/api/forecast/experimental?cutoff=${encodeURIComponent(cutoff)}`),
  assets: () => get<AssetColumns>('/api/assets?format=columnar'),
}
