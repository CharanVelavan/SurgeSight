/** Formatting shared by every panel: IST display times, grouped numbers, compass directions. Latin digits in every language. */

import { currentLocale } from '@/i18n'

const IST = 'Asia/Kolkata'

const cache = new Map<string, Intl.DateTimeFormat>()
function fmt(key: string, options: Intl.DateTimeFormatOptions, locale = currentLocale()): Intl.DateTimeFormat {
  const id = `${key}|${locale}`
  let f = cache.get(id)
  if (!f) cache.set(id, (f = new Intl.DateTimeFormat(`${locale}-u-nu-latn`, options)))
  return f
}
const dayFmt = () => fmt('day', { timeZone: IST, day: '2-digit', month: 'short' })
const timeFmt = () => fmt('time', { timeZone: IST, hour: '2-digit', minute: '2-digit', hour12: false })
const utcFmt = () => fmt('utc', { timeZone: 'UTC', day: '2-digit', hour: '2-digit', hour12: false }, 'en-GB')

/** "04 Dec 14:00 IST" */
export function formatIST(ms: number): string {
  return `${dayFmt().format(ms)} ${timeFmt().format(ms)} IST`
}

export function formatDay(ms: number): string {
  return dayFmt().format(ms)
}

/** "04 Dec 12Z" style label used for GFS cycle names. */
export function formatCycle(ms: number): string {
  const d = new Date(ms)
  const month = fmt('month', { timeZone: 'UTC', month: 'short' }).format(d)
  return `${String(d.getUTCDate()).padStart(2, '0')} ${month} ${String(d.getUTCHours()).padStart(2, '0')}Z`
}

export const utcHour = (ms: number) => utcFmt().format(ms)

export const formatInt = (n: number) => new Intl.NumberFormat(`${currentLocale()}-u-nu-latn`).format(Math.round(n))

const COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']

/** Meteorological direction the wind blows FROM, for u (east) and v (north) components. */
export function windFrom(u: number, v: number): string {
  const deg = (Math.atan2(-u, -v) * 180) / Math.PI
  return COMPASS[Math.round(((deg + 360) % 360) / 22.5) % 16]
}

export function formatLatLon(lat: number, lon: number): string {
  return `${Math.abs(lat).toFixed(2)}°${lat >= 0 ? 'N' : 'S'} ${Math.abs(lon).toFixed(2)}°${lon >= 0 ? 'E' : 'W'}`
}

/** Compass point for a bearing in degrees (the direction something moves towards). */
export function compass(deg: number): string {
  return COMPASS[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16]
}
