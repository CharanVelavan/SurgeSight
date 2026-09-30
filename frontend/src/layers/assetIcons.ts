/**
 * Marker atlas for the map: one disc per facility type and risk class, filled with the risk colour and
 * carrying the facility's icon (the same Lucide icons the lists use). Built once as an SVG and rasterised.
 */

import { Anchor, Cross, Droplet, Flame, GraduationCap, House, ShieldHalf, Zap, type IconNode } from 'lucide'
import { ASSET_ORDER, type AssetType } from '@/data/assets'
import { RISK, type RiskClass } from '@/lib/colors'

const CELL = 64
const CLASSES = Object.keys(RISK) as RiskClass[]
const NODES: Record<AssetType, IconNode> = {
  hospital: Cross, substation: Zap, police_station: ShieldHalf, fire_station: Flame,
  shelter: House, school: GraduationCap, water_facility: Droplet, fishing_harbour: Anchor,
}
/** Dark glyphs on the light discs keep contrast; white on the strong ones. */
const GLYPH: Record<RiskClass, string> = { LOW: '#1B2027', MODERATE: '#1B2027', HIGH: '#FFFFFF', CRITICAL: '#FFFFFF' }

export interface IconMapping {
  [key: string]: { x: number; y: number; width: number; height: number; mask: false; anchorY: number }
}

export const iconKey = (type: string, cls: string) => `${type}:${cls in RISK ? cls : 'LOW'}`

const escape = (v: string) => v.replace(/&/g, '&amp;').replace(/"/g, '&quot;')

function svgAtlas(): { svg: string; mapping: IconMapping; width: number; height: number } {
  const width = CELL * ASSET_ORDER.length
  const height = CELL * CLASSES.length
  const mapping: IconMapping = {}
  const parts: string[] = []
  CLASSES.forEach((cls, row) => {
    ASSET_ORDER.forEach((type, col) => {
      const x = col * CELL, y = row * CELL
      const glyph = NODES[type].map(([tag, attrs]) => `<${tag} ${Object.entries(attrs).map(([k, v]) => `${k}="${escape(String(v))}"`).join(' ')}/>`).join('')
      parts.push(
        `<g transform="translate(${x} ${y})">` +
          `<circle cx="32" cy="32" r="29" fill="rgba(0,0,0,0.28)"/>` +
          `<circle cx="32" cy="31" r="27" fill="${RISK[cls].color}" stroke="#FFFFFF" stroke-width="3.5"/>` +
          `<g transform="translate(17 16) scale(1.25)" fill="none" stroke="${GLYPH[cls]}" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">${glyph}</g>` +
          `</g>`,
      )
      mapping[iconKey(type, cls)] = { x, y, width: CELL, height: CELL, mask: false, anchorY: CELL / 2 }
    })
  })
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${parts.join('')}</svg>`
  return { svg, mapping, width, height }
}

let atlas: { url: string; mapping: IconMapping } | null = null
let started = false

/** The atlas once it has been rasterised; null for the first frames (the map shows dots until then). */
export function assetIconAtlas(): { url: string; mapping: IconMapping } | null {
  if (atlas || started) return atlas
  started = true
  const { svg, mapping, width, height } = svgAtlas()
  const img = new Image()
  img.onload = () => {
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    canvas.getContext('2d')!.drawImage(img, 0, 0)
    atlas = { url: canvas.toDataURL('image/png'), mapping }
  }
  img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
  return null
}
