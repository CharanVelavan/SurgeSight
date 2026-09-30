/** Formatting shared by every panel: IST display times, en-IN grouping, compass directions. */

const IST = 'Asia/Kolkata'

const dayFmt = new Intl.DateTimeFormat('en-IN', { timeZone: IST, day: '2-digit', month: 'short' })
const timeFmt = new Intl.DateTimeFormat('en-IN', { timeZone: IST, hour: '2-digit', minute: '2-digit', hour12: false })
const utcFmt = new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', day: '2-digit', hour: '2-digit', hour12: false })

/** "04 Dec 14:00 IST" */
export function formatIST(ms: number): string {
  return `${dayFmt.format(ms)} ${timeFmt.format(ms)} IST`
}

export function formatDay(ms: number): string {
  return dayFmt.format(ms)
}

/** "04/12Z" style short UTC label used for GFS cycle names. */
export function formatCycle(ms: number): string {
  const d = new Date(ms)
  return `${String(d.getUTCDate()).padStart(2, '0')} ${d.toLocaleString('en', { month: 'short', timeZone: 'UTC' })} ${String(d.getUTCHours()).padStart(2, '0')}Z`
}

export const utcHour = (ms: number) => utcFmt.format(ms)

const intFmt = new Intl.NumberFormat('en-IN')
export const formatInt = (n: number) => intFmt.format(Math.round(n))

const COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']

/** Meteorological direction the wind blows FROM, for u (east) and v (north) components. */
export function windFrom(u: number, v: number): string {
  const deg = (Math.atan2(-u, -v) * 180) / Math.PI
  return COMPASS[Math.round(((deg + 360) % 360) / 22.5) % 16]
}

export function formatLatLon(lat: number, lon: number): string {
  return `${Math.abs(lat).toFixed(2)}°${lat >= 0 ? 'N' : 'S'} ${Math.abs(lon).toFixed(2)}°${lon >= 0 ? 'E' : 'W'}`
}
