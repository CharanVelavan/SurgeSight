/**
 * Network status for weak connections: every data fetch goes through here so the UI can say when it is
 * showing saved data (served by the service worker) and when the data was last fetched fresh.
 */

import { useSyncExternalStore } from 'react'

export interface NetState {
  /** When the copy on screen was saved, if the last response came from the saved copy. */
  savedAt: number | null
  /** Last time any request reached the server. */
  lastFresh: number | null
  mapFailed: boolean
}

let state: NetState = { savedAt: null, lastFresh: null, mapFailed: false }
const listeners = new Set<() => void>()
const set = (patch: Partial<NetState>) => {
  state = { ...state, ...patch }
  listeners.forEach(fn => fn())
}

export const netState = () => state
export const setMapFailed = () => set({ mapFailed: true })

/** A response served from the worker's saved copy carries x-from-cache and the time it was saved. */
export function noteResponse(res: Response): void {
  if (res.headers.get('x-from-cache') === '1') {
    const at = Number(res.headers.get('x-cached-at')) || Date.now()
    set({ savedAt: state.savedAt === null ? at : Math.min(state.savedAt, at) })
  } else if (res.ok) {
    set({ lastFresh: Date.now(), savedAt: null })
  }
}

export async function netFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const res = await fetch(input, init)
  noteResponse(res)
  return res
}

export function useNet(): NetState {
  return useSyncExternalStore(
    fn => {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    () => state,
  )
}

export function useOnline(): boolean {
  return useSyncExternalStore(
    fn => {
      window.addEventListener('online', fn)
      window.addEventListener('offline', fn)
      return () => {
        window.removeEventListener('online', fn)
        window.removeEventListener('offline', fn)
      }
    },
    () => navigator.onLine,
  )
}
