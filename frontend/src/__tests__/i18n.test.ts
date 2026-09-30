import { describe, expect, it } from 'vitest'
import { en } from '@/i18n/en'
import hi from '@/i18n/hi'
import ta from '@/i18n/ta'
import te from '@/i18n/te'
import bn from '@/i18n/bn'
import or from '@/i18n/or'
import { t } from '@/i18n'
import { formatIST } from '@/lib/format'

const locales = { hi, ta, te, bn, or }
const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort()

describe('locales', () => {
  for (const [code, dict] of Object.entries(locales)) {
    it(`${code} has every English key, no extras and the same placeholders`, () => {
      expect(Object.keys(dict).sort()).toEqual(Object.keys(en).sort())
      for (const key of Object.keys(en) as (keyof typeof en)[]) {
        expect(placeholders(dict[key]), `${code}:${key}`).toEqual(placeholders(en[key]))
        expect(dict[key].trim(), `${code}:${key} empty`).not.toBe('')
      }
    })
    it(`${code} keeps numbers in Latin digits`, () => {
      for (const [key, value] of Object.entries(dict)) expect(/[०-९০-৯୦-୯௦-௯౦-౯]/.test(value), `${code}:${key}`).toBe(false)
    })
  }

  it('every locale differs from English for the headline text', () => {
    for (const dict of Object.values(locales)) expect(dict['welcome.title']).not.toBe(en['welcome.title'])
  })
})

describe('t()', () => {
  it('fills placeholders', () => {
    expect(t('app.loadingWeather', { loaded: 3, total: 9 })).toBe('Loading weather 3/9')
  })
  it('formats IST with Latin digits', () => {
    expect(formatIST(Date.UTC(2023, 11, 3, 12))).toBe('03 Dec 17:30 IST')
  })
})
