/* SurgeSight service worker: keeps the app and the last data so a weak connection still shows something.
   - app files (/assets/*, the page): cache first / network first
   - GET /api/*: network first with a timeout, falling back to the last saved copy (marked with x-cached-at)
   - weather images (versioned by ?v=): cache first
   POSTs (explanations, voice) and other origins (Google Maps) are never touched. */
const VERSION = 'v1'
const SHELL = `shell-${VERSION}`
const DATA = `data-${VERSION}`
const TIMEOUT_MS = 6000

self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', event => {
  event.waitUntil(
    (async () => {
      for (const key of await caches.keys()) if (key !== SHELL && key !== DATA) await caches.delete(key)
      await self.clients.claim()
    })(),
  )
})

async function stamp(response) {
  const headers = new Headers(response.headers)
  headers.set('x-cached-at', String(Date.now()))
  return new Response(await response.clone().blob(), { status: response.status, statusText: response.statusText, headers })
}

async function served(response) {
  // a copy from the cache: tell the page it is a saved copy (x-cached-at says when it was saved)
  const headers = new Headers(response.headers)
  headers.set('x-from-cache', '1')
  return new Response(await response.blob(), { status: response.status, statusText: response.statusText, headers })
}

async function networkFirst(request, cacheName, fallbackKey) {
  const cache = await caches.open(cacheName)
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
  try {
    const response = await fetch(request, { signal: ctrl.signal })
    clearTimeout(timer)
    if (response.ok) await cache.put(fallbackKey ?? request, await stamp(response))
    return response
  } catch (err) {
    clearTimeout(timer)
    const hit = await cache.match(fallbackKey ?? request)
    if (hit) return served(hit)
    throw err
  }
}

async function cacheFirst(request, cacheName, dropSamePath) {
  const cache = await caches.open(cacheName)
  const hit = await cache.match(request)
  if (hit) return hit
  const response = await fetch(request)
  if (response.ok) {
    if (dropSamePath) {
      const path = new URL(request.url).pathname
      for (const key of await cache.keys()) if (new URL(key.url).pathname === path) await cache.delete(key)
    }
    await cache.put(request, response.clone())
  }
  return response
}

self.addEventListener('fetch', event => {
  const request = event.request
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(url.pathname.endsWith('.png') ? cacheFirst(request, DATA, true) : networkFirst(request, DATA))
  } else if (url.pathname.startsWith('/assets/')) {
    event.respondWith(cacheFirst(request, SHELL, false))
  } else if (request.mode === 'navigate') {
    // every page is the same app shell
    event.respondWith(networkFirst(request, SHELL, '/index.html'))
  }
})
