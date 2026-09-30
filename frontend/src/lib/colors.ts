/**
 * Perceptual, colour-blind-safe ramps (docs/UI_PLAN.md §3). One definition feeds the GLSL shaders,
 * the legend gradients and the cursor readout so the three can never disagree.
 */

export type Stop = readonly [value: number, hex: string, alpha?: number]

/** Wind speed, m/s, linear. */
export const WIND_RAMP: readonly Stop[] = [
  [0, '#2B4A6F'],
  [5, '#3F8FA6'],
  [10, '#7CC4B0'],
  [17, '#E6D3A3'],
  [25, '#E08A6A'],
  [33, '#B8434A'],
]

/** Rain rate, mm/h, on a log scale; transparent below 0.2 mm/h. */
export const RAIN_RAMP: readonly Stop[] = [
  [0.2, '#4F7CC0', 0],
  [1, '#4F7CC0', 0.55],
  [4, '#6B5FC4', 0.7],
  [10, '#A34FB0', 0.8],
  [25, '#D24A8C', 0.88],
  [50, '#F4D6E4', 0.95],
]

/** Cloud cover, %; clear sky is transparent. */
export const CLOUD_RAMP: readonly Stop[] = [
  [15, '#DDE6F0', 0],
  [40, '#C9D6E6', 0.22],
  [70, '#E3EAF3', 0.42],
  [100, '#F5F8FC', 0.62],
]

/** Cloud cover on the light map: white cloud would vanish there, so it is drawn in slate. */
export const CLOUD_RAMP_LIGHT: readonly Stop[] = [
  [15, '#5E6B7D', 0],
  [40, '#5E6B7D', 0.18],
  [70, '#4A5667', 0.34],
  [100, '#3A4454', 0.5],
]

/** 2 m air temperature, deg C. */
export const TEMP_RAMP: readonly Stop[] = [
  [-10, '#4A6FD0', 0.6],
  [5, '#5DA6D8', 0.55],
  [18, '#7FCB9E', 0.5],
  [28, '#E8D36A', 0.55],
  [36, '#E8853A', 0.6],
  [44, '#C2323F', 0.65],
]

/** Relative humidity, %. */
export const HUMIDITY_RAMP: readonly Stop[] = [
  [20, '#C9A45B', 0.4],
  [50, '#8CBF8A', 0.42],
  [80, '#3F9AA6', 0.5],
  [100, '#2B5FA6', 0.6],
]

export function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

const f = (x: number) => x.toFixed(4)

/**
 * GLSL function `vec4 <name>(float x)` that interpolates the stops piecewise-linearly in `x`.
 * With `log`, interpolation happens in log1p space (used for rain).
 */
export function rampGlsl(name: string, stops: readonly Stop[], log = false): string {
  const t = (v: number) => (log ? Math.log1p(v) : v)
  const lines = [`vec4 ${name}(float value) {`, `  float x = ${log ? 'log(1.0 + max(value, 0.0))' : 'value'};`]
  stops.forEach(([v, hex, a = 1], i) => {
    const [r, g, b] = hexToRgb(hex).map(c => c / 255)
    const col = `vec4(${f(r)}, ${f(g)}, ${f(b)}, ${f(a)})`
    if (i === 0) {
      lines.push(`  vec4 c = ${col};`, `  if (x <= ${f(t(v))}) return c;`)
    } else {
      const [pv] = stops[i - 1]
      lines.push(
        `  if (x <= ${f(t(v))}) return mix(c, ${col}, (x - ${f(t(pv))}) / ${f(t(v) - t(pv))});`,
        `  c = ${col};`,
      )
    }
  })
  lines.push('  return c;', '}')
  return lines.join('\n')
}

/** CSS linear-gradient across the ramp, with stops placed evenly (the legend labels carry the values). */
export function rampCss(stops: readonly Stop[]): string {
  const parts = stops.map(([, hex, a = 1], i) => {
    const [r, g, b] = hexToRgb(hex)
    return `rgba(${r},${g},${b},${Math.max(a, 0.35)}) ${((i / (stops.length - 1)) * 100).toFixed(1)}%`
  })
  return `linear-gradient(90deg, ${parts.join(', ')})`
}

/** Risk classes (docs/UI_PLAN.md §3). Each also has a shape cue so colour is never the only signal. */
export const RISK = {
  LOW: { color: '#9AA5B1', symbol: '○', label: 'Low' },
  MODERATE: { color: '#E0B34A', symbol: '□', label: 'Moderate' },
  HIGH: { color: '#E07B39', symbol: '△', label: 'High' },
  CRITICAL: { color: '#B8322A', symbol: '◆', label: 'Critical' },
} as const

export type RiskClass = keyof typeof RISK
