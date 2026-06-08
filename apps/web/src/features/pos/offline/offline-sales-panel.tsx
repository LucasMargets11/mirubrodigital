'use client';

/**
 * OfflineSalesPanel (PR-OFF-04, redesigned in PR-OFF-06)
 *
 * Owner component for the offline sales queue UI. It holds the single sync
 * instance (manual + auto-sync) and the clear-synced action, then composes:
 * - OfflineSyncStatusPanel: status counts, last sync, "Sincronizar ahora",
 *   "Limpiar sincronizadas".
 * - a detailed list of queued sales (time, total, payment, status, short
 *   client_order_id, server_id when synced, error + "Reintentar" when failed).
 */

import { formatCurrency } from '@/features/cash/utils';
import { usePosOfflineSales } from './offline-sales-hooks';
import {
  usePosClearOfflineSalesHistory,
  usePosOfflineSaleCounts,
  usePosOfflineSync,
  usePosRetryFailedOfflineSales,
} from './offline-sales-sync-hooks';
import { OfflineSyncStatusPanel } from './offline-sync-status-panel';
import {
  describeOfflineSalePayments,
  describeOfflineSaleError,
} from './offline-sale-error';
import { shortClientOrderId } from './offline-sale-id';
import type { OfflineSaleQueueItem, OfflineSaleStatus } from './offline-sales-types';

const STATUS_LABELS: Record<OfflineSaleStatus, string> = {
  pending: 'Pendiente',
  syncing: 'Sincronizando',
  synced: 'Sincronizada',
  failed: 'Error',
  conflict: 'Conflicto',
};

const STATUS_CLASSES: Record<OfflineSaleStatus, string> = {
  pending: 'bg-amber-100 text-amber-800',
  syncing: 'bg-blue-100 text-blue-800',
  synced: 'bg-emerald-100 text-emerald-800',
  failed: 'bg-rose-100 text-rose-800',
  conflict: 'bg-orange-100 text-orange-800',
};

function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat('es-AR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

/** A sale that can be individually retried (failed + still retryable). */
function isRetryable(sale: OfflineSaleQueueItem): boolean {
  return sale.status === 'failed' && sale.retryable !== false;
}

export function OfflineSalesPanel() {
  const { data, isLoading } = usePosOfflineSales();
  const counts = usePosOfflineSaleCounts();
  const { sync, isSyncing, isOnline, lastRun, syncableCount } = usePosOfflineSync();
  const { clearHistory, isClearing } = usePosClearOfflineSalesHistory();
  const { retryErrors, isRetrying } = usePosRetryFailedOfflineSales();

  const sales = data ?? [];

  if (isLoading) {
    return (
      <section aria-label="Ventas offline pendientes" className="rounded-2xl border border-slate-200 bg-white p-4">
        <p className="text-sm text-slate-400">Cargando ventas pendientes…</p>
      </section>
    );
  }

  if (sales.length === 0) {
    return null;
  }

  return (
    <section
      aria-label="Ventas offline pendientes"
      className="rounded-2xl border border-slate-200 bg-white p-4"
    >
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900">Ventas offline</h2>
        <span
          data-testid="offline-pending-count"
          className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800"
        >
          Ventas pendientes: {counts.pending}
        </span>
      </header>

      <OfflineSyncStatusPanel
        counts={counts}
        lastRun={lastRun}
        isSyncing={isSyncing}
        isOnline={isOnline}
        isClearing={isClearing}
        isRetryingErrors={isRetrying}
        syncableCount={syncableCount}
        onSync={sync}
        onClearHistory={clearHistory}
        onRetryErrors={retryErrors}
      />

      <ul className="divide-y divide-slate-100">
        {sales.map((sale) => {
          const errorMessage = describeOfflineSaleError(sale);
          const retryable = isRetryable(sale);
          return (
            <li
              key={sale.local_id}
              data-testid="offline-sale-row"
              className="flex flex-col gap-1 py-2.5 text-sm"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 space-y-0.5">
                  <p className="font-mono text-xs text-slate-500">
                    #{shortClientOrderId(sale.client_order_id)}
                  </p>
                  <p className="text-xs text-slate-400">{formatTime(sale.created_at)}</p>
                  <p className="text-xs text-slate-500">
                    {describeOfflineSalePayments(sale.payment_snapshot)}
                  </p>
                  {sale.status === 'synced' && sale.server_id ? (
                    <p
                      data-testid="offline-sale-server-id"
                      className="font-mono text-xs text-emerald-600"
                    >
                      Servidor: {shortClientOrderId(sale.server_id)}
                    </p>
                  ) : null}
                </div>
                <div className="flex flex-col items-end gap-1">
                  <span className="font-semibold tabular-nums text-slate-800">
                    {formatCurrency(sale.totals_snapshot.total)}
                  </span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_CLASSES[sale.status]}`}
                  >
                    {STATUS_LABELS[sale.status]}
                  </span>
                </div>
              </div>

              {errorMessage ? (
                <div className="flex items-center justify-between gap-3">
                  <p
                    data-testid="offline-sale-error"
                    className="text-xs text-rose-600"
                  >
                    {errorMessage}
                  </p>
                  {retryable ? (
                    <button
                      type="button"
                      onClick={() => sync()}
                      disabled={!isOnline || isSyncing}
                      className="shrink-0 rounded-lg border border-rose-200 px-2.5 py-1 text-xs font-medium text-rose-600 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Reintentar
                    </button>
                  ) : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
