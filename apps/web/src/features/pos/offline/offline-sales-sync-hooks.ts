'use client';

/**
 * TanStack Query hooks for the offline POS sale sync engine (PR-OFF-05).
 *
 * - usePosOfflineSync()        → manual "Sincronizar ahora" mutation + auto-sync
 *                                on reconnect. Reads the employee token and
 *                                online state, then drains the IndexedDB queue.
 * - usePosOfflineSaleCounts()  → derived pending/failed/synced/conflict counts.
 *
 * The mutation submits each queued sale to POST /api/v1/pos/sales/ using
 * `client_order_id` for idempotency (no duplicates on retry).
 */

import { useEffect, useMemo, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { useEmployeeSession } from '../context';
import { useNetworkStatus } from '@/hooks/use-network-status';
import { posCreateSaleFromOffline } from '@/lib/api/pos';
import {
  clearResolvedAndErroredOfflineSales,
  getOfflineSalesStorage,
  resetRetryableFailedOfflineSales,
} from './offline-sales-store';
import {
  isSyncableSale,
  syncOfflineSales,
  type SyncRunResult,
} from './offline-sales-sync';
import { posOfflineSalesKeys, usePosOfflineSales } from './offline-sales-hooks';
import type { OfflineSaleQueueItem } from './offline-sales-types';

export interface OfflineSaleCounts {
  total: number;
  pending: number;
  syncing: number;
  synced: number;
  failed: number;
  conflict: number;
  /** Sales eligible for a sync run (pending + retryable failed). */
  syncable: number;
  /** `failed` sales still marked retryable (clearable via "Reintentar errores"). */
  retryableFailed: number;
  /** Sales removable by "Limpiar historial" (synced + failed + conflict). */
  clearable: number;
  /** ISO timestamp of the most recent successful sync, or null if none. */
  lastSyncedAt: string | null;
}

/** Derives status counts from the queued offline sales. */
export function usePosOfflineSaleCounts(): OfflineSaleCounts {
  const { data } = usePosOfflineSales();
  return useMemo(() => countOfflineSales(data ?? []), [data]);
}

function countOfflineSales(sales: OfflineSaleQueueItem[]): OfflineSaleCounts {
  const counts: OfflineSaleCounts = {
    total: sales.length,
    pending: 0,
    syncing: 0,
    synced: 0,
    failed: 0,
    conflict: 0,
    syncable: 0,
    retryableFailed: 0,
    clearable: 0,
    lastSyncedAt: null,
  };
  for (const sale of sales) {
    if (sale.status === 'pending') counts.pending += 1;
    else if (sale.status === 'syncing') counts.syncing += 1;
    else if (sale.status === 'synced') counts.synced += 1;
    else if (sale.status === 'failed') {
      counts.failed += 1;
      if (sale.retryable !== false) counts.retryableFailed += 1;
    } else if (sale.status === 'conflict') counts.conflict += 1;
    if (
      sale.status === 'synced' ||
      sale.status === 'failed' ||
      sale.status === 'conflict'
    ) {
      counts.clearable += 1;
    }
    if (isSyncableSale(sale)) counts.syncable += 1;
    if (
      sale.synced_at &&
      (counts.lastSyncedAt === null || sale.synced_at > counts.lastSyncedAt)
    ) {
      counts.lastSyncedAt = sale.synced_at;
    }
  }
  return counts;
}

export interface UsePosOfflineSyncResult {
  /** Triggers a sync run manually (e.g. "Sincronizar ahora" button). */
  sync: () => void;
  isSyncing: boolean;
  isOnline: boolean;
  /** Summary of the last completed run, or undefined before the first run. */
  lastRun: SyncRunResult | undefined;
  /** Number of sales eligible for sync right now. */
  syncableCount: number;
}

/**
 * Manual + automatic offline sale synchronisation.
 *
 * Auto-sync fires exactly once on each offline→online transition when there are
 * eligible sales, guarded against overlapping runs. The manual `sync()` reuses
 * the same mutation. The engine itself is a no-op when offline or already busy.
 */
export function usePosOfflineSync(): UsePosOfflineSyncResult {
  const { session } = useEmployeeSession();
  const token = session.status === 'authenticated' ? session.token : null;
  const { isOnline } = useNetworkStatus();
  const queryClient = useQueryClient();
  const counts = usePosOfflineSaleCounts();

  const mutation = useMutation<SyncRunResult, Error, void>({
    networkMode: 'always',
    mutationFn: async () => {
      if (!token) throw new Error('No hay token de sesión operativa');
      return syncOfflineSales({
        storage: getOfflineSalesStorage(),
        submit: (payload) => posCreateSaleFromOffline(token, payload),
        isOnline,
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: posOfflineSalesKeys.list() });
    },
  });

  const { mutate, isPending } = mutation;

  // Auto-sync on the offline→online edge. The ref tracks the previous online
  // value so this fires at most once per reconnection, never in a loop. A
  // manual `sync()` (or a later reconnect) drains anything left over.
  const wasOnlineRef = useRef(isOnline);
  const syncableCount = counts.syncable;
  useEffect(() => {
    const wasOnline = wasOnlineRef.current;
    wasOnlineRef.current = isOnline;
    if (!wasOnline && isOnline && syncableCount > 0 && !isPending && token) {
      mutate();
    }
  }, [isOnline, syncableCount, isPending, token, mutate]);

  return {
    sync: () => mutate(),
    isSyncing: isPending,
    isOnline,
    lastRun: mutation.data,
    syncableCount,
  };
}

export interface UsePosClearHistoryResult {
  /** Removes `synced`, `failed` and `conflict` sales from the local queue. */
  clearHistory: () => void;
  isClearing: boolean;
  /** Number of sales removed by the last clear, or undefined before any run. */
  lastClearedCount: number | undefined;
}

/**
 * Mutation that clears the offline panel history (PR-OFF-11): it removes
 * `synced`, `failed` and `conflict` sales from the local queue so resolved
 * sales and errors disappear from the panel. It NEVER touches `pending` or
 * `syncing` sales (those still need to reach the backend). Refreshes the queue
 * query on completion.
 */
export function usePosClearOfflineSalesHistory(): UsePosClearHistoryResult {
  const queryClient = useQueryClient();
  const mutation = useMutation<number, Error, void>({
    networkMode: 'always',
    mutationFn: () => clearResolvedAndErroredOfflineSales(getOfflineSalesStorage()),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: posOfflineSalesKeys.list() });
    },
  });

  return {
    clearHistory: () => mutation.mutate(),
    isClearing: mutation.isPending,
    lastClearedCount: mutation.data,
  };
}

export interface UsePosRetryFailedResult {
  /** Returns retryable `failed` sales to `pending` and clears their error. */
  retryErrors: () => void;
  isRetrying: boolean;
  /** Number of sales reset by the last run, or undefined before any run. */
  lastRetriedCount: number | undefined;
}

/**
 * Mutation that recovers retryable `failed` offline sales (PR-OFF-09): it sends
 * them back to `pending` and clears `last_error` so they re-enter the sync
 * queue. It NEVER deletes a sale, and leaves `conflict` and non-retryable
 * `failed` sales untouched (those require explicit review). Refreshes the queue
 * query on completion so the next reconnect/manual sync picks them up.
 */
export function usePosRetryFailedOfflineSales(): UsePosRetryFailedResult {
  const queryClient = useQueryClient();
  const mutation = useMutation<number, Error, void>({
    networkMode: 'always',
    mutationFn: () => resetRetryableFailedOfflineSales(getOfflineSalesStorage()),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: posOfflineSalesKeys.list() });
    },
  });

  return {
    retryErrors: () => mutation.mutate(),
    isRetrying: mutation.isPending,
    lastRetriedCount: mutation.data,
  };
}
