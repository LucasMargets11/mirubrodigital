'use client';

/**
 * TanStack Query hooks for the offline POS sale queue (PR-OFF-04).
 *
 * - usePosOfflineSales()        → reads queued sales from IndexedDB.
 * - usePosOfflineSalesCount()   → convenience pending counter.
 * - usePosCaptureOfflineSale()  → validates + persists a captured sale locally.
 *
 * These hooks NEVER call the backend. Syncing arrives in PR-OFF-05.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  enqueueOfflineSale,
  getOfflineSalesStorage,
  listOfflineSales,
} from './offline-sales-store';
import {
  buildOfflineSale,
  validateOfflineSale,
  type OfflineSaleInput,
} from './offline-sale-build';
import { countUnsyncedOfflineSales } from './offline-snapshot-policy';
import type { OfflineSaleQueueItem } from './offline-sales-types';

export const posOfflineSalesKeys = {
  list: () => ['pos', 'offline', 'sales'] as const,
};

/** Reads the locally-queued offline sales (newest first). */
export function usePosOfflineSales() {
  return useQuery<OfflineSaleQueueItem[]>({
    queryKey: posOfflineSalesKeys.list(),
    queryFn: () => listOfflineSales(),
    staleTime: Infinity,
    // IndexedDB reads must work offline.
    networkMode: 'always',
  });
}

/** Pending-sales counter derived from the queue. */
export function usePosOfflineSalesCount(): number {
  const query = usePosOfflineSales();
  return (query.data ?? []).filter((s) => s.status === 'pending').length;
}

export class OfflineSaleValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'OfflineSaleValidationError';
  }
}

/**
 * Captures and persists an offline sale. Validates against the snapshot rules
 * first; on failure it rejects with {@link OfflineSaleValidationError} and does
 * NOT write anything. On success the queue query is refreshed.
 */
export function usePosCaptureOfflineSale() {
  const queryClient = useQueryClient();

  return useMutation<OfflineSaleQueueItem, Error, OfflineSaleInput>({
    networkMode: 'always',
    mutationFn: async (input) => {
      const storage = getOfflineSalesStorage();
      // Enforce the PR-OFF-07 guardrails at capture time against live data:
      // current clock for snapshot expiry, live queue size for the pending cap.
      const queued = await listOfflineSales(storage);
      const enriched: OfflineSaleInput = {
        ...input,
        now: new Date().toISOString(),
        unsyncedCount: countUnsyncedOfflineSales(queued),
      };
      const validation = validateOfflineSale(enriched);
      if (validation.ok === false) {
        throw new OfflineSaleValidationError(validation.message);
      }
      const item = buildOfflineSale(enriched);
      return enqueueOfflineSale(item, storage);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: posOfflineSalesKeys.list() });
    },
  });
}
