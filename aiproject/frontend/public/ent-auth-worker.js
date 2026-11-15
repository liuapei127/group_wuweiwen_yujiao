// Keep authentication requests alive until their cookies have been processed.
// Only serialize the three operations that change the employee session cookies.
const sessionMutations = new Set([
  '/api/v1/auth/login',
  '/api/v1/auth/refresh',
  '/api/v1/auth/logout',
])
let pending = Promise.resolve()

self.addEventListener('install', event => event.waitUntil(self.skipWaiting()))
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()))

self.addEventListener('fetch', event => {
  const request = event.request
  const url = new URL(request.url)
  if (request.method !== 'POST' || url.origin !== self.location.origin ||
      !sessionMutations.has(url.pathname)) return

  const headers = new Headers(request.headers)
  const body = url.pathname.endsWith('/login') ? request.text() : undefined
  const result = pending.then(async () => fetch(url.href, {
    method: 'POST',
    // Build a new request after waiting so the browser attaches the latest cookie.
    headers,
    body: await body,
    credentials: 'same-origin',
    cache: 'no-store',
    redirect: 'error',
  }))
  pending = result.then(() => {}, () => {})
  event.respondWith(result)
  // A navigation can drop the response consumer before the cookie rotation completes.
  event.waitUntil(pending)
})
