'use client';

/**
 * PosPwaRegistrar — wires the POS PWA shell (PR-OFF-01).
 *
 * Responsibilities (scoped to /pos only):
 * 1. Inject the `<link rel="manifest">` and `<meta name="theme-color">` tags so
 *    the browser can offer installation while inside the POS. React hoists these
 *    head elements automatically. They are only rendered on /pos routes, so the
 *    rest of the app (/app, /m, /r) is unaffected.
 * 2. Register the service worker with an explicit `/pos/` scope, so the worker
 *    never controls pages outside the POS.
 *
 * No offline storage or sync is set up here — that is future work (PR-OFF-02+).
 */

import { useEffect } from 'react';

/** Critical POS routes to keep warm so "+ Venta" can open while offline. */
const CRITICAL_POS_ROUTES = ['/pos/login', '/pos/terminal', '/pos/terminal/new-sale'];

export function PosPwaRegistrar() {
  useEffect(() => {
    if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) {
      return;
    }

    /**
     * Ask the active worker to pre-cache the critical POS navigation documents
     * while we are online, so an offline "+ Venta" can open the sale screen.
     * Best-effort: failures are non-fatal.
     */
    function warmPosRoutes() {
      if (typeof navigator === 'undefined' || !navigator.onLine) return;
      navigator.serviceWorker.ready
        .then((registration) => {
          registration.active?.postMessage({
            type: 'CACHE_POS_ROUTES',
            urls: CRITICAL_POS_ROUTES,
          });
        })
        .catch(() => {
          // Worker not ready yet — non-fatal, will retry on next 'online' event.
        });
    }

    // Register against the static worker at the origin root but restrict its
    // control to the /pos/ scope only.
    navigator.serviceWorker
      .register('/sw.js', { scope: '/pos/' })
      .then(() => warmPosRoutes())
      .catch(() => {
        // Registration failures are non-fatal: the POS still works online.
      });

    window.addEventListener('online', warmPosRoutes);
    return () => window.removeEventListener('online', warmPosRoutes);
  }, []);

  return (
    <>
      <link rel="manifest" href="/manifest.webmanifest" />
      <meta name="theme-color" content="#4f46e5" />
    </>
  );
}
