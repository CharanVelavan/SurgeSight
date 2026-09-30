/** One icon per facility type, shared by lists and the map markers (layers/assetIcons.ts uses the same names). */

import { Anchor, Cross, Droplet, Flame, GraduationCap, House, ShieldHalf, Zap, type LucideIcon } from 'lucide-react'
import type { AssetType } from './assets'

export const ASSET_ICON: Record<AssetType, LucideIcon> = {
  hospital: Cross,
  substation: Zap,
  police_station: ShieldHalf,
  fire_station: Flame,
  shelter: House,
  school: GraduationCap,
  water_facility: Droplet,
  fishing_harbour: Anchor,
}
