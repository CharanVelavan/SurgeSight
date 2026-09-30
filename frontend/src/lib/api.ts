import { netFetch } from '@/lib/net'
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
  osm_element: string[]
  osm_id: number[]
  risk_class: string[]
  risk_score: number[]
  triage_tier: number[]
  dominant_hazard: string[]
  /** 'hospital' for real hospitals, otherwise clinics and other health facilities (hospital rows only). */
  facility_quality?: (string | null)[]
}

export interface AssetFacts {
  name: string
  asset_type: string
  class: string
  score: number
  triage_tier: number
  rank_percentile: number
  driving_hazard: string
  elevation_m: number | null
  waterlogging: { terrain_flood_score: number | null; level: string; rain_forecast_mm: number | null; rain_flood_score: number | null }
  wind_peak_kmh: number | null
  surge_m: number | null
  surge_score: number | null
  hazard_contributions: Record<string, number | null>
  distance: { closest_approach_km: number; closest_approach_time_utc: string; distance_at_time_km: number | null; distance_at_time_note: string }
  model_version: string
  disclaimer: string
}

export interface AssetExplanation {
  facts: AssetFacts
  text: { summary: string; reasons: string[] } | null
  text_source: 'gemini' | 'template' | null
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
  const res = await netFetch(path)
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`)
  return (await res.json()) as T
}

async function post<T>(path: string): Promise<T> {
  const res = await fetch(path, { method: 'POST' })
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`)
  return (await res.json()) as T
}

export interface AdvisoryAsset {
  name: string
  asset_type: string
  risk_class?: string
  [key: string]: unknown
}

export interface Advisory {
  audience: string
  severity: string
  headline: string
  situation_summary: string
  instruction: string
  priority_actions: string[]
  critical_assets: AdvisoryAsset[]
  monitoring_priorities: string[]
  disclaimer: string
  language: string
}

export interface DispatchItem {
  id: string
  department: string
  channel: 'chat' | 'email' | 'push'
  subject: string
  status: string
  created_at_utc: string
  sent_at_utc: string | null
  mode: string | null
  attachment_names: string[]
}

export interface ParametricTrigger { id: string; label: string; index_value: number; breached: boolean; payout_pct: number; probability?: number }
export interface ParametricPortfolio {
  id: string
  name: string
  districts: string[]
  insured_sites: number
  triggers: ParametricTrigger[]
  payout_pct: number
  sum_insured_crore: number
  payout_crore: number
  expected_payout_crore?: number
  payout_p10_crore?: number
  payout_p90_crore?: number
}
export interface Parametric {
  label: string
  portfolios: ParametricPortfolio[]
  ensemble?: { members: number; expected_total_payout_crore: number }
  total_payout_crore: number
  total_sum_insured_crore: number
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`)
  return (await res.json()) as T
}

export interface CatalogTile {
  id: string
  kind: 'live' | 'storm'
  name: string
  year?: number
  blurb: string
  status: 'available' | 'soon'
  category?: string
  month?: string
  states?: string
}

export const api = {
  advisory: (department: string, language: string) => postJson<{ run_id: string; advisory: Advisory }>('/api/advisory', { department, language }),
  dispatches: () => get<DispatchItem[]>('/api/dispatch'),
  parametric: () => postJson<{ run_id: string; data: Parametric }>('/api/parametric/baseline', { members: 40 }),
  capUrl: (runId: string) => `/api/cap/${encodeURIComponent(runId)}`,
  speech: async (runId: string, language: string) => {
    const res = await fetch('/api/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ advisory_run_id: runId, language }) })
    if (!res.ok) throw new Error(`speech: HTTP ${res.status}`)
    return URL.createObjectURL(await res.blob())
  },
  catalog: () => get<{ tiles: CatalogTile[] }>('/api/catalog'),
  timeline: () => get<Timeline>('/api/timeline'),
  forecast: (cutoff: string) => get<ExperimentalForecast>(`/api/forecast/experimental?cutoff=${encodeURIComponent(cutoff)}`),
  explain: (element: string, id: number, time: string, cutoff: string, narrative: boolean, language: string) =>
    post<AssetExplanation>(`/api/assets/${element}/${id}/explain?time=${encodeURIComponent(time)}&cutoff=${encodeURIComponent(cutoff)}&narrative=${narrative}&language=${language}`),
  assets: () => get<AssetColumns>('/api/assets?format=columnar'),
}
