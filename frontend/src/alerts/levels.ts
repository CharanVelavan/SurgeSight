/**
 * Alert levels for places the pages list: every facility, and each district in the study area, at one valid
 * time. The severity grid is the same one the map draws, so a list and the map can never disagree.
 */

import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useStore } from 'zustand'
import { assetsStore } from '@/data/assets'
import { trackStore } from '@/data/track'
import { weatherStore } from '@/weather/atlas'
import type { Manifest } from '@/weather/manifest'
import { alertField } from './field'
import { stormAt } from './storm'

export interface LevelGrid {
  sev: Float32Array
  manifest: Manifest
}

let cacheKey = ''
let cacheGrid: LevelGrid | null = null

/** Severity grid at a valid time (forecast rain after the cutoff, never observed). Cached per hour. */
export function levelGrid(time: number, cutoff: number): LevelGrid | null {
  const { manifest, atlases, loaded, total } = weatherStore.getState()
  if (!manifest || !total || loaded < total) return null
  const { timeline, forecast } = trackStore.getState()
  const key = `${Math.round(time / 3_600_000)}|${cutoff}|${forecast ? 'f' : '-'}|${atlases.size}`
  if (key !== cacheKey) {
    cacheKey = key
    cacheGrid = { sev: alertField(manifest, time, cutoff, 'forecast', stormAt(timeline?.track, forecast, time, cutoff)), manifest }
  }
  return cacheGrid
}

/** 0 green .. 3 red at a point (nearest grid node). */
export function levelAt(g: LevelGrid, lon: number, lat: number): number {
  const { west, north, step } = g.manifest.bounds
  const { width: W, height: H } = g.manifest.tile
  const x = Math.round((lon - west) / step), y = Math.round((north - lat) / step)
  if (x < 0 || y < 0 || x >= W || y >= H) return 0
  return Math.min(3, Math.floor(g.sev[y * W + x]))
}

/** Level of every facility at the time; recomputed when the time moves by an hour or the data arrives. */
export function useAssetLevels(time: number, cutoff: number): Uint8Array | null {
  const data = useStore(assetsStore, s => s.data)
  const loaded = useStore(weatherStore, s => s.loaded)
  const forecast = useStore(trackStore, s => s.forecast)
  const [levels, setLevels] = useState<Uint8Array | null>(null)
  const hour = Math.round(time / 3_600_000)
  useEffect(() => {
    const g = levelGrid(hour * 3_600_000, cutoff)
    if (!g || !data) return setLevels(null)
    const out = new Uint8Array(data.count)
    for (let i = 0; i < data.count; i++) out[i] = levelAt(g, data.lon[i], data.lat[i])
    setLevels(out)
  }, [data, loaded, forecast, hour, cutoff])
  return levels
}

// --- districts ----------------------------------------------------------------------------------------

type Ring = number[][]
export interface District {
  name: string
  state: string
  population: number | null
  polygons: Ring[][]
  bbox: [number, number, number, number]
}

function polygonsOf(geom: { type: string; coordinates?: unknown; geometries?: { type: string; coordinates?: unknown }[] }): Ring[][] {
  if (geom.type === 'Polygon') return [geom.coordinates as Ring[]]
  if (geom.type === 'MultiPolygon') return geom.coordinates as Ring[][]
  if (geom.type === 'GeometryCollection') return (geom.geometries ?? []).flatMap(polygonsOf)
  return []
}

function inRing(lon: number, lat: number, ring: Ring): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j]
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

export function inDistrict(d: District, lon: number, lat: number): boolean {
  const [w, s, e, n] = d.bbox
  if (lon < w || lon > e || lat < s || lat > n) return false
  return d.polygons.some(p => inRing(lon, lat, p[0]) && !p.slice(1).some(h => inRing(lon, lat, h)))
}

async function fetchDistricts(): Promise<District[]> {
  const res = await fetch('/api/layers/districts')
  if (!res.ok) throw new Error(`districts: HTTP ${res.status}`)
  const fc = (await res.json()) as { features: { properties: Record<string, unknown>; geometry: Parameters<typeof polygonsOf>[0] }[] }
  return fc.features.map(f => {
    const polygons = polygonsOf(f.geometry)
    const pts = polygons.flatMap(p => p[0])
    const lons = pts.map(p => p[0]), lats = pts.map(p => p[1])
    return {
      name: String(f.properties.district ?? f.properties.name ?? '?'),
      state: String(f.properties.state ?? ''),
      population: typeof f.properties.population === 'number' ? f.properties.population : null,
      polygons,
      bbox: [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)],
    }
  })
}

export const useDistricts = () => useQuery({ queryKey: ['districts'], queryFn: fetchDistricts, staleTime: Infinity })

export interface AreaRow {
  district: District
  level: number
  facilities: number
  critical: number
  high: number
}

/** Each district's highest level at the time (over the grid nodes inside it) and its facilities by class. */
export function areaRows(districts: District[], g: LevelGrid | null): AreaRow[] {
  const data = assetsStore.getState().data
  return districts.map(d => {
    let level = 0
    if (g) {
      const { west, north, step } = g.manifest.bounds
      const [w, s, e, n] = d.bbox
      for (let lat = Math.ceil(s / step) * step; lat <= n; lat += step)
        for (let lon = Math.ceil(w / step) * step; lon <= e; lon += step)
          if (inDistrict(d, lon, lat)) level = Math.max(level, levelAt(g, lon, lat))
      // small districts can fall between grid nodes: use the centre as well
      level = Math.max(level, levelAt(g, (w + e) / 2, (s + n) / 2))
      void west, void north
    }
    let facilities = 0, critical = 0, high = 0
    if (data)
      for (let i = 0; i < data.count; i++)
        if (inDistrict(d, data.lon[i], data.lat[i])) {
          facilities++
          if (data.riskClass[i] === 'CRITICAL') critical++
          else if (data.riskClass[i] === 'HIGH') high++
        }
    return { district: d, level, facilities, critical, high }
  })
}
