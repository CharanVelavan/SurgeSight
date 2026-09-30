/** Glyph atlas for infrastructure markers, drawn once on a canvas: a ring around a solid glyph. */

import { ASSET_ORDER, ASSET_TYPES, type AssetType } from '@/data/assets'

const CELL = 64

type Ctx = CanvasRenderingContext2D

const GLYPHS: Record<(typeof ASSET_TYPES)[AssetType]['glyph'], (c: Ctx) => void> = {
  cross: c => {
    c.fillRect(27, 14, 10, 36)
    c.fillRect(14, 27, 36, 10)
  },
  bolt: c => {
    c.beginPath()
    c.moveTo(36, 10)
    c.lineTo(20, 35)
    c.lineTo(30, 35)
    c.lineTo(27, 54)
    c.lineTo(44, 28)
    c.lineTo(34, 28)
    c.closePath()
    c.fill()
  },
  shield: c => {
    c.beginPath()
    c.moveTo(32, 12)
    c.lineTo(48, 18)
    c.lineTo(46, 36)
    c.quadraticCurveTo(44, 47, 32, 53)
    c.quadraticCurveTo(20, 47, 18, 36)
    c.lineTo(16, 18)
    c.closePath()
    c.fill()
  },
  flame: c => {
    c.beginPath()
    c.moveTo(32, 10)
    c.quadraticCurveTo(52, 30, 44, 44)
    c.quadraticCurveTo(38, 54, 32, 54)
    c.quadraticCurveTo(24, 54, 20, 44)
    c.quadraticCurveTo(14, 32, 32, 10)
    c.fill()
  },
  house: c => {
    c.beginPath()
    c.moveTo(32, 12)
    c.lineTo(52, 30)
    c.lineTo(46, 30)
    c.lineTo(46, 50)
    c.lineTo(18, 50)
    c.lineTo(18, 30)
    c.lineTo(12, 30)
    c.closePath()
    c.fill()
  },
  diamond: c => {
    c.beginPath()
    c.moveTo(32, 12)
    c.lineTo(51, 32)
    c.lineTo(32, 52)
    c.lineTo(13, 32)
    c.closePath()
    c.fill()
  },
  drop: c => {
    c.beginPath()
    c.moveTo(32, 10)
    c.quadraticCurveTo(50, 32, 46, 42)
    c.arc(32, 42, 14, 0, Math.PI, false)
    c.quadraticCurveTo(14, 32, 32, 10)
    c.fill()
  },
  hex: c => {
    c.beginPath()
    for (let i = 0; i < 6; i++) {
      const a = (Math.PI / 3) * i - Math.PI / 6
      c.lineTo(32 + 20 * Math.cos(a), 32 + 20 * Math.sin(a))
    }
    c.closePath()
    c.fill()
  },
}

export interface IconMapping {
  [type: string]: { x: number; y: number; width: number; height: number; mask: true }
}

let cached: { url: string; mapping: IconMapping } | null = null

export function assetIconAtlas(): { url: string; mapping: IconMapping } {
  if (cached) return cached
  const canvas = document.createElement('canvas')
  canvas.width = CELL * ASSET_ORDER.length
  canvas.height = CELL
  const c = canvas.getContext('2d')!
  const mapping: IconMapping = {}
  ASSET_ORDER.forEach((type, i) => {
    c.save()
    c.translate(i * CELL, 0)
    c.fillStyle = '#fff'
    c.strokeStyle = '#fff'
    // ring + solid glyph, both tinted by the layer colour (mask icons)
    c.lineWidth = 6
    c.beginPath()
    c.arc(32, 32, 27, 0, Math.PI * 2)
    c.stroke()
    c.save()
    c.translate(32, 32)
    c.scale(0.7, 0.7)
    c.translate(-32, -32)
    GLYPHS[ASSET_TYPES[type].glyph](c)
    c.restore()
    c.restore()
    mapping[type] = { x: i * CELL, y: 0, width: CELL, height: CELL, mask: true }
  })
  cached = { url: canvas.toDataURL('image/png'), mapping }
  return cached
}
