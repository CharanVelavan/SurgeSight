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

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`)
  return (await res.json()) as T
}

export const api = {
  timeline: () => get<Timeline>('/api/timeline'),
  assets: () => get<AssetColumns>('/api/assets?format=columnar'),
}
