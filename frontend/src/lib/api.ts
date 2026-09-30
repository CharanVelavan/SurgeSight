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
  /** Road access after the most-exposed sections are removed in the screening (absent without a road layer). */
  road_access?: (RoadAccess | null)[]
  hospital_km_before?: (number | null)[]
  hospital_km_after?: (number | null)[]
}

export type RoadAccess = 'open' | 'at_risk' | 'cut_off' | 'not_assessed'

/** Main-road sections at watch level or above, as parallel columns (/api/roads). */
export interface RoadColumns {
  model_version: string
  count: number
  names: string[]
  /** Flat lon, lat pairs; section i runs from starts[i] to starts[i + 1] (in points). */
  path: number[]
  starts: number[]
  id: string[]
  name: number[]
  /** 0 motorway, 1 trunk, 2 primary, 3 secondary, 4 tertiary. */
  highway: number[]
  level: number[]
  cause: ('flood' | 'surge' | 'wind')[]
  km: number[]
  rain_mm: (number | null)[]
  wind_kmh: (number | null)[]
  surge_m: (number | null)[]
  elevation_min_m: (number | null)[]
  hand_min_m: (number | null)[]
  district: (string | null)[]
}

export interface RoadSummary {
  km_total: number
  km_by_level: Record<'open' | 'watch' | 'high_exposure' | 'most_exposed', number>
  km_level2plus_by_district: Record<string, number>
  top_roads: { road: string; km: number; level: number; highway: string }[]
  access_counts: Record<string, Partial<Record<RoadAccess, number>>>
  hospital_detour: { facilities_with_longer_trip: number; facilities_without_hospital_after: number }
  validation: {
    sections_observed: number
    km_observed: number
    observed_flooded_share: number | null
    auc_water_on_road: number | null
    by_flood_level: Record<string, { sections: number; observed_flooded_share: number | null }>
  }
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
  detail?: any
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

export interface NowCity {
  city: string
  condition: string | null
  temperature_c: number | null
  rain_probability_pct: number | null
  wind_kmh: number | null
  gust_kmh: number | null
}

export const api = {
  advisory: (department: string, language: string, run_id?: string | null) => postJson<{ run_id: string; advisory: Advisory }>('/api/advisory', { department, language, run_id }),
  dispatches: () => get<DispatchItem[]>('/api/dispatch'),
  parametric: () => postJson<{ run_id: string; data: Parametric }>('/api/parametric/baseline', { members: 40 }),
  capUrl: (runId: string) => `/api/cap/${encodeURIComponent(runId)}`,
  speech: async (runId: string, language: string) => {
    const res = await fetch('/api/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ advisory_run_id: runId, language }) })
    if (!res.ok) throw new Error(`speech: HTTP ${res.status}`)
    return URL.createObjectURL(await res.blob())
  },
  liveNow: () => get<{ cities: NowCity[]; source: string }>('/api/live/now'),
  catalog: () => get<{ tiles: CatalogTile[] }>('/api/catalog'),
  timeline: () => get<Timeline>('/api/timeline'),
  forecast: (cutoff: string) => get<ExperimentalForecast>(`/api/forecast/experimental?cutoff=${encodeURIComponent(cutoff)}`),
  explain: (element: string, id: number, time: string, cutoff: string, narrative: boolean, language: string) =>
    post<AssetExplanation>(`/api/assets/${element}/${id}/explain?time=${encodeURIComponent(time)}&cutoff=${encodeURIComponent(cutoff)}&narrative=${narrative}&language=${language}`),
  assets: () => get<AssetColumns>('/api/assets?format=columnar'),
  roads: () => get<RoadColumns>('/api/roads'),
  roadSummary: () => get<RoadSummary>('/api/roads/summary'),
  recipients: (department: string) => get<string[]>(`/api/recipients?department=${encodeURIComponent(department)}`),
  addRecipient: (department: string, email: string) => postJson<string[]>('/api/recipients', { department, email }),
  removeRecipient: (department: string, email: string) => fetch(`/api/recipients?department=${encodeURIComponent(department)}&email=${encodeURIComponent(email)}`, { method: 'DELETE' }).then(r => { if (!r.ok) throw new Error(); return r.json() as Promise<string[]> }),
  dispatchMode: () => get<{ mode: string; provider_configured: string }>('/api/dispatch/mode'),
  queueDispatch: (advisory_run_id: string, channel: string = 'email') => postJson<{ data: { dispatch_id: string } }>('/api/dispatch', { advisory_run_id, channel, include_cap: true }),
  approveDispatch: (id: string) => postJson<DispatchItem>(`/api/dispatch/${encodeURIComponent(id)}/approve`, {}),
  rejectDispatch: (id: string) => postJson<DispatchItem>(`/api/dispatch/${encodeURIComponent(id)}/reject`, {}),
  sendDispatch: (id: string) => postJson<DispatchItem>(`/api/dispatch/${encodeURIComponent(id)}/send`, {}),
  me: () => get<{ uid: string; email: string; role: string; department: string | null; auth_mode?: string }>('/api/me'),
}
