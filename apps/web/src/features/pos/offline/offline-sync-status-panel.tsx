'use client';

/**
 * OfflineSyncStatusPanel (PR-OFF-05, redesigned in PR-OFF-06)
 *
 * Presentational summary header for the offline sales queue:
 * - status counts (pending / syncing / synced / failed / conflict)
 * - last successful sync timestamp
 * - manual "Sincronizar ahora" action (disabled + "Sin conexión" when offline)
 * - "Limpiar sincronizadas" action (only when there are synced sales)
 * - result message of the last sync run
 *
 * It holds no state and calls no hooks: OfflineSalesPanel (the owner) injects
 * data and callbacks so there is a single source of truth for sync/auto-sync.
 */

import { RefreshCw, RotateCcw, Trash2 } from 'lucide-react';
import type { SyncRunResult } from './offline-sales-sync';
import type { OfflineSaleCounts } from './offline-sales-sync-hooks';

const SYNC_SUCCESS = 'Ventas sincronizadas correctamente';
const SYNC_PARTIAL = 'Algunas ventas no pudieron sincronizarse';
const RETRY_ERRORS_HINT =
  'Los errores reintentables volverán a Pendiente para sincronizarse de nuevo.';
const CLEAR_HISTORY_HINT =
  'Se eliminarán del panel las ventas sincronizadas y las ventas con error. Las pendientes no se borran.';

export interface OfflineSyncStatusPanelProps {
  counts: OfflineSaleCounts;
  lastRun: SyncRunResult | undefined;
  isSyncing: boolean;
  isOnline: boolean;
  isClearing: boolean;
  isRetryingErrors: boolean;
  /** Sales eligible for a sync run right now (pending + retryable failed). */
  syncableCount: number;
  onSync: () => void;
  onClearHistory: () => void;
  onRetryErrors: () => void;
}

function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat('es-AR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function OfflineSyncStatusPanel({
  counts,
  lastRun,
  isSyncing,
  isOnline,
  isClearing,
  isRetryingErrors,
  syncableCount,
  onSync,
  onClearHistory,
  onRetryErrors,
}: OfflineSyncStatusPanelProps) {
  const showSyncButton = syncableCount > 0;
  const syncDisabled = !isOnline || isSyncing;
  const syncLabel = !isOnline
    ? 'Sin conexión'
    : isSyncing
      ? 'Sincronizando…'
      : 'Sincronizar ahora';

  const showClearButton = counts.clearable > 0;
  const showRetryErrorsButton = counts.retryableFailed > 0;

  const runMessage = (() => {
    if (!lastRun || !lastRun.ran || isSyncing) return null;
    const hadProblems =
      lastRun.failed > 0 || lastRun.conflicts > 0 || lastRun.stoppedOnError;
    if (lastRun.synced > 0 && !hadProblems) {
      return { tone: 'success' as const, text: SYNC_SUCCESS };
    }
    if (hadProblems) {
      return { tone: 'partial' as const, text: SYNC_PARTIAL };
    }
    return null;
  })();

  return (
    <div className="mb-3 space-y-2" data-testid="offline-sync-status">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span
          data-testid="offline-count-pending"
          className="rounded-full bg-amber-100 px-2.5 py-0.5 font-medium text-amber-800"
        >
          Pendientes: {counts.pending}
        </span>
        <span
          data-testid="offline-count-syncing"
          className="rounded-full bg-blue-100 px-2.5 py-0.5 font-medium text-blue-800"
        >
          Sincronizando: {counts.syncing}
        </span>
        <span
          data-testid="offline-count-synced"
          className="rounded-full bg-emerald-100 px-2.5 py-0.5 font-medium text-emerald-800"
        >
          Sincronizadas: {counts.synced}
        </span>
        <span
          data-testid="offline-count-failed"
          className="rounded-full bg-rose-100 px-2.5 py-0.5 font-medium text-rose-800"
        >
          Fallidas: {counts.failed}
        </span>
        <span
          data-testid="offline-count-conflict"
          className="rounded-full bg-orange-100 px-2.5 py-0.5 font-medium text-orange-800"
        >
          Conflictos: {counts.conflict}
        </span>
      </div>

      <p data-testid="offline-last-sync" className="text-xs text-slate-500">
        {counts.lastSyncedAt
          ? `Última sincronización: ${formatDateTime(counts.lastSyncedAt)}`
          : 'Todavía no se sincronizó ninguna venta'}
      </p>

      <div className="flex flex-wrap items-center gap-2">
        {showSyncButton ? (
          <button
            type="button"
            onClick={onSync}
            disabled={syncDisabled}
            className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${isSyncing ? 'animate-spin' : ''}`}
              aria-hidden="true"
            />
            {syncLabel}
          </button>
        ) : null}

        {showClearButton ? (
          <button
            type="button"
            onClick={onClearHistory}
            disabled={isClearing}
            title={CLEAR_HISTORY_HINT}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
            {isClearing ? 'Limpiando…' : 'Limpiar historial'}
          </button>
        ) : null}

        {showRetryErrorsButton ? (
          <button
            type="button"
            onClick={onRetryErrors}
            disabled={isRetryingErrors}
            title={RETRY_ERRORS_HINT}
            className="inline-flex items-center gap-2 rounded-lg border border-amber-200 px-3 py-1.5 text-xs font-medium text-amber-700 transition hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            {isRetryingErrors ? 'Reintentando…' : 'Reintentar errores'}
          </button>
        ) : null}
      </div>

      {showRetryErrorsButton ? (
        <p className="text-xs text-slate-500">{RETRY_ERRORS_HINT}</p>
      ) : null}

      {showClearButton ? (
        <p className="text-xs text-slate-500">{CLEAR_HISTORY_HINT}</p>
      ) : null}

      {runMessage ? (
        <p
          role="status"
          className={
            runMessage.tone === 'success'
              ? 'text-xs font-medium text-emerald-700'
              : 'text-xs font-medium text-amber-700'
          }
        >
          {runMessage.text}
        </p>
      ) : null}
    </div>
  );
}
