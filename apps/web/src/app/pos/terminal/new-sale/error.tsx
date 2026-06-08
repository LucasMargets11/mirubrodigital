'use client';

/**
 * Error boundary for /pos/terminal/new-sale (PR-OFF-08).
 *
 * If the route's JS chunk cannot be loaded — typically when navigating offline
 * to a screen that was never prepared while online — Next.js throws a
 * ChunkLoadError. Instead of a broken screen, we show a controlled message and
 * a way back to the terminal.
 */

import { useEffect } from 'react';

function isChunkLoadError(error: Error): boolean {
  return (
    error.name === 'ChunkLoadError' ||
    /Loading chunk|ChunkLoadError|importing a module script failed/i.test(
      error.message,
    )
  );
}

export default function PosNewSaleError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const chunkError = isChunkLoadError(error);

  // Hard navigation so the service worker serves the precached /pos/terminal
  // shell. A client-side router push would re-attempt the failed RSC/chunk
  // fetch and could hang the cashier offline (PR-OFF-09).
  const goToTerminal = () => {
    if (typeof window !== 'undefined') {
      window.location.assign('/pos/terminal');
    }
  };

  useEffect(() => {
    // Surface non-chunk errors to the console for debugging.
    if (!chunkError) {
      console.error('PosNewSale error boundary:', error);
    }
  }, [error, chunkError]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <div className="max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <h1 className="text-lg font-semibold text-slate-900">
          {chunkError ? 'Sin conexión' : 'Algo salió mal'}
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-slate-500">
          {chunkError
            ? 'Esta pantalla todavía no está disponible offline. Conectate una vez para prepararla.'
            : 'No pudimos abrir la pantalla de venta. Intentá de nuevo.'}
        </p>
        <div className="mt-6 flex justify-center gap-3">
          {chunkError ? (
            <button
              type="button"
              onClick={goToTerminal}
              className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-indigo-700"
            >
              Volver al terminal
            </button>
          ) : (
            <button
              type="button"
              onClick={() => reset()}
              className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-indigo-700"
            >
              Reintentar
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
