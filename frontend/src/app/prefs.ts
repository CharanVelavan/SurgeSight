/**
 * Per-viewer preferences kept in this browser: role, theme, map defaults. They are conveniences only; the app
 * works the same when storage is blocked (the choices then last for the visit).
 */

import { useEffect, useSyncExternalStore } from 'react'
import { create } from 'zustand'
import { persist, type StateStorage, createJSONStorage } from 'zustand/middleware'

export type Theme = 'system' | 'light' | 'dark'
export type RoleId = 'collector' | 'health' | 'fire_rescue' | 'electricity' | 'police' | 'water' | 'fisheries'

export interface Prefs {
  onboarded: boolean
  role: RoleId
  theme: Theme
  /** Weather layers switched on when a storm map opens. The alert zones are always on at first. */
  stormWind: boolean
  stormRain: boolean
  /** Fewer wind particles and no fly-in: for slow devices and weak batteries. */
  lite: boolean
  set: (patch: Partial<Omit<Prefs, 'set'>>) => void
}

const safeStorage: StateStorage = {
  getItem: k => {
    try {
      return localStorage.getItem(k)
    } catch {
      return null
    }
  },
  setItem: (k, v) => {
    try {
      localStorage.setItem(k, v)
    } catch {
      /* storage blocked: keep the value in memory only */
    }
  },
  removeItem: k => {
    try {
      localStorage.removeItem(k)
    } catch {
      /* ignore */
    }
  },
}

export const usePrefs = create<Prefs>()(
  persist(
    set => ({
      onboarded: false,
      role: 'collector',
      theme: 'system',
      stormWind: true,
      stormRain: true,
      lite: false,
      set: patch => set(patch),
    }),
    {
      name: 'surgesight.prefs',
      storage: createJSONStorage(() => safeStorage),
      version: 2,
      // v1 had the storm wind off by default; v2 turns it back on for everyone once.
      migrate: (old, version) => (version < 2 ? { ...(old as object), stormWind: true } : old) as Prefs,
    },
  ),
)

const darkQuery = () => matchMedia('(prefers-color-scheme: dark)')

function systemDark(): boolean {
  return useSyncExternalStore(
    fn => {
      const q = darkQuery()
      q.addEventListener('change', fn)
      return () => q.removeEventListener('change', fn)
    },
    () => darkQuery().matches,
  )
}

/** 'light' or 'dark' after resolving 'system'. */
export function useResolvedTheme(): 'light' | 'dark' {
  const theme = usePrefs(s => s.theme)
  const sys = systemDark()
  return theme === 'system' ? (sys ? 'dark' : 'light') : theme
}

/** Keeps the <html> classes (theme, and `lite`, which turns off page motion) and the browser chrome colour in step. */
export function useApplyTheme(): void {
  const resolved = useResolvedTheme()
  const lite = usePrefs(s => s.lite)
  useEffect(() => {
    document.documentElement.classList.toggle('dark', resolved === 'dark')
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', resolved === 'dark' ? '#081226' : '#F8FAFD')
  }, [resolved])
  useEffect(() => {
    document.documentElement.classList.toggle('lite', lite)
  }, [lite])
}
