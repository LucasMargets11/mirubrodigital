'use client';

/**
 * Offline data status card for the POS terminal (PR-OFF-02B).
 *
 * Shows the state of the locally-persisted offline snapshot and lets the
 * employee refresh it on demand. This is informational + download only — it
 * does NOT enable offline sales.
 */

import { usePosOfflineBootstrapDownload, usePosOfflineSnapshot } from './bootstrap-hooks';

function formatSavedAt(savedAt: string): string {
  const date = new Date(savedAt);
  if (Number.isNaN(date.getTime())) {
    return savedAt;
  }
  return new Intl.DateTimeFormat('es-AR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function PosOfflineStatusCard() {
  const snapshotQuery = usePosOfflineSnapshot();
  const download = usePosOfflineBootstrapDownload();

  const snapshot = snapshotQuery.data ?? null;
  const offlineEnabled = snapshot?.offline_policy.enabled ?? true;
  const hasNoCashSession = snapshot != null && snapshot.cash_session == null;

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      <header className="mb-3">
        <h2 className="text-base font-semibold text-gray-900">Datos offline del POS</h2>
        <p className="text-sm text-gray-500">
          Snapshot local para operar en contingencia (solo lectura por ahora).
        </p>
      </header>

      {snapshotQuery.isLoading ? (
        <p className="text-sm text-gray-500">Cargando datos offline…</p>
      ) : snapshot ? (
        <dl className="mb-4 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-gray-500">Última actualización</dt>
            <dd className="font-medium text-gray-900">{formatSavedAt(snapshot.saved_at)}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Productos disponibles</dt>
            <dd className="font-medium text-gray-900">{snapshot.products.length}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Métodos de pago</dt>
            <dd className="font-medium text-gray-900">{snapshot.payment_methods.length}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Categorías</dt>
            <dd className="font-medium text-gray-900">{snapshot.categories.length}</dd>
          </div>
        </dl>
      ) : (
        <p className="mb-4 text-sm text-gray-600">
          Todavía no descargaste datos para contingencia.
        </p>
      )}

      {!offlineEnabled && (
        <p className="mb-4 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Modo offline no habilitado para este negocio.
        </p>
      )}

      {hasNoCashSession && (
        <p className="mb-4 rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-800">
          No hay caja abierta; las ventas offline no estarán disponibles hasta abrir caja.
        </p>
      )}

      <button
        type="button"
        onClick={() => download.mutate()}
        disabled={download.isPending}
        className="inline-flex items-center justify-center rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {download.isPending ? 'Actualizando…' : 'Actualizar datos offline'}
      </button>

      {download.isError && (
        <p className="mt-3 text-sm text-red-600">
          No se pudieron actualizar los datos offline. Se conservó la última descarga.
        </p>
      )}
      {download.isSuccess && !download.isPending && (
        <p className="mt-3 text-sm text-green-700">Datos offline actualizados.</p>
      )}
    </section>
  );
}
