/** Fixed camera frames. Fitting is computed per viewport so the same geography shows on any screen. */

export interface Box { west: number; south: number; east: number; north: number }

/** The national frame: Arabian Sea and the Gulf on the left, Myanmar and the South China Sea on the right. */
export const INDIA: Box = { west: 46, south: -2, east: 118, north: 40 }
/** Coast where the screened infrastructure sits (Chennai to Nellore), with margin. */
export const IMPACT: Box = { west: 78.4, south: 10.6, east: 82.6, north: 17.4 }
/** Panning limit while zoomed into the impact area. */
export const IMPACT_LIMIT: Box = { west: 76, south: 9, east: 85, north: 20 }

const mercY = (lat: number) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360))

export function fitCamera(box: Box, width: number, height: number) {
  const dx = ((box.east - box.west) / 360) * 256
  const dy = (mercY(box.north) - mercY(box.south)) / (2 * Math.PI) * 256
  const zoom = Math.log2(Math.min(width / dx, height / dy))
  const yc = (mercY(box.north) + mercY(box.south)) / 2
  return { zoom, center: { lat: (2 * Math.atan(Math.exp(yc)) - Math.PI / 2) * (180 / Math.PI), lng: (box.west + box.east) / 2 } }
}
