/** A small path router: the app has a handful of screens and needs no routing library. */

import { useSyncExternalStore } from 'react'

export type StormTab = 'overview' | 'map' | 'facilities' | 'areas' | 'roads' | 'advisories'
export const STORM_TABS: StormTab[] = ['overview', 'map', 'facilities', 'areas', 'roads', 'advisories']

export type Route =
  | { name: 'home' }
  | { name: 'welcome' }
  | { name: 'live' }
  | { name: 'storm'; id: string; tab: StormTab }
  | { name: 'guide' }
  | { name: 'settings' }

export function parseRoute(path: string): Route {
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent)
  switch (parts[0]) {
    case undefined:
      return { name: 'home' }
    case 'welcome':
      return { name: 'welcome' }
    case 'live':
      return { name: 'live' }
    case 'guide':
      return { name: 'guide' }
    case 'settings':
      return { name: 'settings' }
    case 'storm':
      if (parts[1] && (parts.length === 2 || (parts.length === 3 && STORM_TABS.includes(parts[2] as StormTab))))
        return { name: 'storm', id: parts[1], tab: (parts[2] as StormTab) ?? 'overview' }
  }
  return { name: 'home' }
}

export function pathFor(r: Route): string {
  switch (r.name) {
    case 'home':
      return '/'
    case 'storm':
      return `/storm/${encodeURIComponent(r.id)}${r.tab === 'overview' ? '' : `/${r.tab}`}`
    default:
      return `/${r.name}`
  }
}

const listeners = new Set<() => void>()
const subscribe = (fn: () => void) => {
  listeners.add(fn)
  window.addEventListener('popstate', fn)
  return () => {
    listeners.delete(fn)
    window.removeEventListener('popstate', fn)
  }
}

export function navigate(path: string, replace = false): void {
  if (path === location.pathname + location.search) return
  if (replace) history.replaceState(null, '', path)
  else history.pushState(null, '', path)
  listeners.forEach(fn => fn())
}

const snapshot = () => location.pathname

export function useRoute(): Route {
  return parseRoute(useSyncExternalStore(subscribe, snapshot))
}

/** Client-side navigation that still allows middle-click and "open in new tab". */
export function onLinkClick(e: React.MouseEvent<HTMLAnchorElement>, path: string): void {
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
  e.preventDefault()
  navigate(path)
}

/** An <a> that navigates inside the app. */
export function Link({ to, ...props }: Omit<React.ComponentProps<'a'>, 'href'> & { to: string }) {
  return <a href={to} {...props} onClick={e => { props.onClick?.(e); if (!e.defaultPrevented) onLinkClick(e, to) }} />
}
