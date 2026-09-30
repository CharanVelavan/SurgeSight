/** A minimal path router: three screens do not need a routing library. */

import { useSyncExternalStore } from 'react'

export type Route = { name: 'landing' } | { name: 'live' } | { name: 'storm'; id: string }

export function parseRoute(path: string): Route {
  const parts = path.split('/').filter(Boolean)
  if (parts[0] === 'live' && parts.length === 1) return { name: 'live' }
  if (parts[0] === 'storm' && parts.length === 2) return { name: 'storm', id: decodeURIComponent(parts[1]) }
  return { name: 'landing' }
}

export const pathFor = (r: Route): string => (r.name === 'landing' ? '/' : r.name === 'live' ? '/live' : `/storm/${encodeURIComponent(r.id)}`)

const listeners = new Set<() => void>()
const subscribe = (fn: () => void) => {
  listeners.add(fn)
  window.addEventListener('popstate', fn)
  return () => {
    listeners.delete(fn)
    window.removeEventListener('popstate', fn)
  }
}

export function navigate(path: string): void {
  if (path === location.pathname) return
  history.pushState(null, '', path)
  listeners.forEach(fn => fn())
}

const snapshot = () => location.pathname

export function useRoute(): Route {
  return parseRoute(useSyncExternalStore(subscribe, snapshot))
}

/** A link that navigates without a reload but still works with middle-click and "open in new tab". */
export function onLinkClick(e: React.MouseEvent<HTMLAnchorElement>, path: string): void {
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
  e.preventDefault()
  navigate(path)
}
