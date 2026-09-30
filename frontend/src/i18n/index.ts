/** Interface language: a tiny store, `t()` for text and `useT()` so components re-render when it changes. */

import { useSyncExternalStore } from 'react'
import { en, type Key } from './en'

export type Lang = 'en' | 'hi' | 'ta' | 'te' | 'bn' | 'or'

export const LANGS: { code: Lang; native: string; api: 'English' | 'Hindi' | 'Tamil' | 'Telugu' | 'Bengali' | 'Odia'; locale: string }[] = [
  { code: 'en', native: 'English', api: 'English', locale: 'en-IN' },
  { code: 'hi', native: 'हिन्दी', api: 'Hindi', locale: 'hi-IN' },
  { code: 'ta', native: 'தமிழ்', api: 'Tamil', locale: 'ta-IN' },
  { code: 'te', native: 'తెలుగు', api: 'Telugu', locale: 'te-IN' },
  { code: 'bn', native: 'বাংলা', api: 'Bengali', locale: 'bn-IN' },
  { code: 'or', native: 'ଓଡ଼ିଆ', api: 'Odia', locale: 'or-IN' },
]

type Dict = Record<Key, string>
const loaders: Record<Exclude<Lang, 'en'>, () => Promise<{ default: Dict }>> = {
  hi: () => import('./hi'),
  ta: () => import('./ta'),
  te: () => import('./te'),
  bn: () => import('./bn'),
  or: () => import('./or'),
}

const STORAGE_KEY = 'surgesight.lang'
const listeners = new Set<() => void>()
let lang: Lang = 'en'
let dict: Dict = en

function stored(): Lang | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    return LANGS.some(l => l.code === v) ? (v as Lang) : null
  } catch {
    return null
  }
}

function announce() {
  document.documentElement.lang = lang
  listeners.forEach(fn => fn())
}

export async function setLang(next: Lang): Promise<void> {
  try {
    localStorage.setItem(STORAGE_KEY, next)
  } catch {
    /* storage can be blocked; the choice then lasts for this visit only */
  }
  dict = next === 'en' ? en : (await loaders[next]()).default
  lang = next
  announce()
}

/** Reads the saved choice at start-up. Missing keys in a locale fall back to English at lookup. */
export async function initLang(): Promise<void> {
  const saved = stored()
  if (saved && saved !== 'en') await setLang(saved)
  else announce()
}

export const currentLang = () => lang
export const currentLocale = () => LANGS.find(l => l.code === lang)!.locale
export const currentApiLanguage = () => LANGS.find(l => l.code === lang)!.api

export function t(key: Key, params?: Record<string, string | number>): string {
  let s: string = dict[key] ?? en[key] ?? key
  if (params) for (const [k, v] of Object.entries(params)) s = s.replaceAll(`{${k}}`, String(v))
  return s
}

const subscribe = (fn: () => void) => {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

/** Returns `t` bound to the current language; the component re-renders when the language changes. */
export function useT(): typeof t {
  useSyncExternalStore(subscribe, currentLang)
  return t
}

export function useLang(): Lang {
  return useSyncExternalStore(subscribe, currentLang)
}

export type { Key }
