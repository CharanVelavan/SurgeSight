/**
 * Who uses SurgeSight and which facilities each role looks after. Mirrors config/departments.toml
 * (a test keeps the two in step); the words are in the locale files under role.<id>.*.
 */

import { Anchor, Droplets, Flame, HeartPulse, Landmark, ShieldHalf, Zap, type LucideIcon } from 'lucide-react'
import type { RoleId } from '@/app/prefs'
import type { AssetType } from './assets'

export interface Role {
  id: RoleId
  icon: LucideIcon
  types: AssetType[]
  /** Only real hospitals (not clinics) count for this role, as in departments.toml facility_quality. */
  hospitalsOnly?: boolean
}

export const ROLES: Role[] = [
  { id: 'collector', icon: Landmark, types: ['shelter', 'hospital', 'substation', 'school', 'fire_station', 'police_station', 'water_facility', 'fishing_harbour'] },
  { id: 'health', icon: HeartPulse, types: ['hospital'] },
  { id: 'fire_rescue', icon: Flame, types: ['fire_station', 'hospital'], hospitalsOnly: true },
  { id: 'electricity', icon: Zap, types: ['substation'] },
  { id: 'police', icon: ShieldHalf, types: ['police_station'] },
  { id: 'water', icon: Droplets, types: ['water_facility'] },
  { id: 'fisheries', icon: Anchor, types: ['fishing_harbour'] },
]

export const roleById = (id: RoleId): Role => ROLES.find(r => r.id === id) ?? ROLES[0]

/** Whether facility i belongs to the role's list. */
export function inRole(role: Role, type: string, quality: string | null | undefined): boolean {
  if (!role.types.includes(type as AssetType)) return false
  return !(role.hospitalsOnly && type === 'hospital' && quality !== 'hospital')
}

/** Real hospitals ahead of clinics, then by score: the order departments.py uses. */
export const priorityRank = (type: string, quality: string | null | undefined) => (type === 'hospital' && quality !== 'hospital' ? 1 : 0)
