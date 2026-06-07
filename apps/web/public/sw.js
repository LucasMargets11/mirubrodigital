/*
 * MiRubro POS — Service Worker (PR-OFF-01, hardened in PR-OFF-08)
 *
 * Purpose: cache the POS *shell* so the app is installable as a PWA and the
 * basic UI can load when there is no connection. This is the technical base for
 * the offline contingency mode.
 *
 * IMPORTANT — scope & boundaries:
 * - This worker is registered with scope "/pos/" (see PosPwaRegistrar.tsx), so it
 *   only controls pages under /pos/. It never controls /app, /m or /r.
 * - It only ever caches same-origin GET shell/static assets.
 * - It NEVER caches the API (cross-origin, NEXT_PUBLIC_API_URL) nor any /api path,
 *   so tokens, sales, cash and other sensitive data are never stored here.
 *
 * PR-OFF-08 hardening:
 * - The `fetch` handler NEVER resolves to `undefined` (that throws a TypeError:
 *   "Failed to convert value to Response"). Every branch returns a Response.
 * - `/_next/static` uses a safe cache-first strategy (hashed, immutable assets).
 * - On a navigation miss while offline we serve a controlled fallback page
 *   instead of a broken ChunkLoadError screen.
 */

const CACHE_VERSION = 'v2';
const CACHE_NAME = `mirubro-pos-shell-${CACHE_VERSION}`;

// Minimal shell entry points to pre-cache on install. Best-effort: a failure to
// fetch any of these must not abort the install. `/pos/terminal` is the POS home
// and the priority navigation fallback (PR-OFF-11), so we warm it eagerly.
const SHELL_URLS = [
  '/pos/terminal',
  '/pos/login',
  '/manifest.webmanifest',
  '/favicon.ico',
];

// Critical POS routes we try to keep warm so "+ Venta" works offline.
const POS_ROUTE_PREFIX = '/pos';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) =>
        Promise.allSettled(SHELL_URLS.map((url) => cache.add(url))),
      )
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith('mirubro-pos-shell-') && key !== CACHE_NAME)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

/**
 * Lets the app ask the worker to warm critical POS routes while online, so the
 * navigation document is available offline (chunks are cached on demand by the
 * cache-first static handler as the prefetched route loads them).
 */
self.addEventListener('message', (event) => {
  const data = event.data;
  if (data && data.type === 'CACHE_POS_ROUTES' && Array.isArray(data.urls)) {
    event.waitUntil(cachePosRoutes(data.urls));
  }
});

async function cachePosRoutes(urls) {
  const cache = await caches.open(CACHE_NAME);
  const safe = urls.filter(
    (url) => typeof url === 'string' && url.startsWith(POS_ROUTE_PREFIX),
  );
  // Best-effort: a single failure must not reject the whole batch.
  await Promise.allSettled(safe.map((url) => cache.add(url)));
}

/**
 * Returns true for same-origin GET requests that are safe to cache as part of
 * the POS shell. Explicitly excludes the API and anything outside our control.
 */
function isCacheableStatic(request, url) {
  if (request.method !== 'GET') return false;
  if (url.origin !== self.location.origin) return false; // cross-origin (API) → never
  if (url.pathname.startsWith('/api')) return false; // same-origin API → never
  return (
    url.pathname.startsWith('/_next/static') ||
    url.pathname.startsWith('/logo') ||
    url.pathname.startsWith('/images') ||
    url.pathname === '/manifest.webmanifest' ||
    url.pathname === '/favicon.ico' ||
    url.pathname === '/apple-touch-icon.png'
  );
}

/**
 * Controlled offline fallback shown when a /pos navigation cannot be served from
 * the network nor the cache. Never throws; always a valid HTML Response.
 */
function offlineFallbackResponse() {
  const html = `<!DOCTYPE html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Sin conexión — MiRubro POS</title>
    <style>
      body { font-family: system-ui, sans-serif; margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #f8fafc; color: #0f172a; }
      .card { max-width: 28rem; margin: 1.5rem; padding: 2rem; background: #fff; border: 1px solid #e2e8f0; border-radius: 1rem; text-align: center; box-shadow: 0 1px 2px rgba(0,0,0,.05); }
      h1 { font-size: 1.125rem; margin: 0 0 .75rem; }
      p { font-size: .9rem; color: #475569; margin: 0 0 1.25rem; line-height: 1.5; }
      a { display: inline-block; padding: .6rem 1.1rem; border-radius: .75rem; background: #4f46e5; color: #fff; text-decoration: none; font-size: .85rem; font-weight: 600; }
    </style>
  </head>
  <body>
    <div class="card">
      <h1>Sin conexión</h1>
      <p>Esta pantalla todavía no está disponible offline. Conectate una vez para prepararla.</p>
      <a href="/pos/terminal">Volver al terminal</a>
    </div>
  </body>
</html>`;
  return new Response(html, {
    status: 200,
    headers: { 'Content-Type': 'text/html; charset=utf-8' },
  });
}

/**
 * Navigations within /pos → network-first, with safe offline fallbacks.
 * ALWAYS resolves to a Response.
 *
 * Offline fallback order (PR-OFF-11): we must NEVER prefer /pos/login over
 * /pos/terminal for a navigation that started inside /pos/terminal/*, otherwise
 * "Volver atrás" from new-sale would drop the cashier back to login.
 *   a. the exact cached request
 *   b. the precached /pos/terminal shell
 *   c. the precached /pos/terminal/new-sale shell
 *   d. the precached /pos/login shell
 *   e. a controlled offline fallback HTML page
 */
async function handleNavigate(request) {
  try {
    const response = await fetch(request);
    // Cache a copy for offline use (best-effort, never blocks the response).
    const copy = response.clone();
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.put(request, copy))
      .catch(() => {});
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    const terminalShell = await caches.match('/pos/terminal');
    if (terminalShell) return terminalShell;
    const newSaleShell = await caches.match('/pos/terminal/new-sale');
    if (newSaleShell) return newSaleShell;
    const loginShell = await caches.match('/pos/login');
    if (loginShell) return loginShell;
    return offlineFallbackResponse();
  }
}

/**
 * Static shell assets → cache-first (hashed/immutable). ALWAYS resolves to a
 * Response: cache hit, network result, or a controlled network-error Response.
 */
async function handleStatic(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response && response.ok) {
      const copy = response.clone();
      caches
        .open(CACHE_NAME)
        .then((cache) => cache.put(request, copy))
        .catch(() => {});
    }
    return response;
  } catch {
    // No cache + network failure: return a controlled error Response so the
    // browser sees a normal failed fetch instead of a worker TypeError.
    return Response.error();
  }
}

self.addEventListener('fetch', (event) => {
  const { request } = event;

  let url;
  try {
    url = new URL(request.url);
  } catch {
    return; // Malformed URL → let the browser handle it.
  }

  // Never intercept cross-origin requests (this is where the API lives).
  if (url.origin !== self.location.origin) return;

  // Never intercept the API — tokens / sales / cash must always hit the network.
  if (url.pathname.startsWith('/api')) return;

  // Navigations within /pos → network-first, fall back to cached shell offline.
  if (request.mode === 'navigate' && url.pathname.startsWith(POS_ROUTE_PREFIX)) {
    event.respondWith(handleNavigate(request));
    return;
  }

  // Static shell assets → cache-first so the shell renders offline.
  if (isCacheableStatic(request, url)) {
    event.respondWith(handleStatic(request));
  }
});

// Test-only export hook. In the service-worker runtime `module` is undefined, so
// this block is skipped and has no effect on production behavior.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    isCacheableStatic,
    handleNavigate,
    handleStatic,
    offlineFallbackResponse,
    cachePosRoutes,
    CACHE_NAME,
  };
}
