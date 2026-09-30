import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { ROLES } from '@/data/roles'
import { parseRoute, pathFor } from '@/app/router'

describe('roles', () => {
  it('match config/departments.toml (ids and facility types)', () => {
    const toml = readFileSync(new URL('../../../config/departments.toml', import.meta.url), 'utf8')
    const blocks = [...toml.matchAll(/\[departments\.(\w+)\][\s\S]*?asset_types = \[([^\]]*)\]/g)]
    const fromToml = Object.fromEntries(blocks.map(m => [m[1], [...m[2].matchAll(/"(\w+)"/g)].map(x => x[1]).sort()]))
    const fromTs = Object.fromEntries(ROLES.map(r => [r.id, [...r.types].sort()]))
    expect(fromTs).toEqual(fromToml)
  })
})

describe('router', () => {
  it('round-trips every screen', () => {
    for (const path of ['/', '/welcome', '/live', '/guide', '/settings', '/storm/michaung_2023', '/storm/michaung_2023/map', '/storm/michaung_2023/facilities', '/storm/michaung_2023/areas'])
      expect(pathFor(parseRoute(path))).toBe(path)
    expect(parseRoute('/storm/x/nope')).toEqual({ name: 'home' })
  })
})
