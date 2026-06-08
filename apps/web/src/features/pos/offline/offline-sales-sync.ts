/**
 * Offline POS sale sync engine (PR-OFF-05).
 *
 * Pure, framework-free logic that drains the local IndexedDB queue and submits
 * each pending/retryable sale to the backend via an injected `submit` function.
 * Decoupled from React/network/token so it can be unit-tested directly.
 *
 * Guarantees:
 * - Only syncs when online and when no run is already in flight.
 * - Never syncs `synced` sales; never auto-syncs `conflict` sales.
 * - Processes sales oldest-first (created_at ASC), one at a time.
 * - Cuts the loop on network/server/auth failures to avoid request storms.
 * - Never mutates `client_order_id`; never recalculates prices.
 */

import type {
  OfflineSalePayload,
  OfflineSaleQueueItem,
  OfflineSaleStatus,
  OfflineSaleSyncResult,
} from './offline-sales-types';
import { getOfflineSalesStorage, type OfflineSalesStorage } from './offline-sales-store';

/** Submits one offline sale payload to the backend. */
export type OfflineSaleSubmit = (
  payload: OfflineSalePayload,
) => Promise<OfflineSaleSyncResult>;

export type SyncErrorKind =
  | 'network'
  | 'server'
  | 'auth'
  | 'validation'
  | 'conflict';

export interface SyncErrorClassification {
  kind: SyncErrorKind;
  /** Target status to persist for the offline sale. */
  status: Extract<OfflineSaleStatus, 'pending' | 'failed' | 'conflict'>;
  /** Whether the sale may be retried later. */
  retryable: boolean;
  /** Whether to stop processing the rest of the queue this run. */
  stopLoop: boolean;
  /** Human-readable detail stored in `last_error`. */
  message: string;
}

export interface SyncRunResult {
  /** False when skipped because offline or a run was already in flight. */
  ran: boolean;
  attempted: number;
  synced: number;
  failed: number;
  conflicts: number;
  /** True when the loop was cut short by a transient/auth error. */
  stoppedOnError: boolean;
}

// ── Error classification ──────────────────────────────────────────────────────

function getErrorStatus(error: unknown): number | null {
  if (error && typeof error === 'object' && 'status' in error) {
    const status = (error as { status: unknown }).status;
    if (typeof status === 'number') return status;
  }
  return null;
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

/**
 * Maps a submit error to a persistence decision. Network errors (no HTTP
 * status) and 5xx/auth errors stop the loop; 400/409 are per-sale and let the
 * loop continue with the next sale.
 */
export function classifySyncError(error: unknown): SyncErrorClassification {
  const status = getErrorStatus(error);

  // No HTTP status → network/timeout failure.
  if (status === null) {
    return {
      kind: 'network',
      status: 'pending',
      retryable: true,
      stopLoop: true,
      message: 'Sin conexión al sincronizar. Se reintentará automáticamente.',
    };
  }

  if (status === 401 || status === 403) {
    return {
      kind: 'auth',
      status: 'failed',
      retryable: false,
      stopLoop: true,
      message: 'La sesión POS ya no está autorizada.',
    };
  }

  if (status === 409) {
    return {
      kind: 'conflict',
      status: 'conflict',
      retryable: false,
      stopLoop: false,
      message: getErrorMessage(error, 'La venta entró en conflicto con el servidor.'),
    };
  }

  if (status >= 500) {
    return {
      kind: 'server',
      status: 'failed',
      retryable: true,
      stopLoop: true,
      message: getErrorMessage(error, 'Error del servidor al sincronizar. Se reintentará.'),
    };
  }

  // Any other 4xx (400, 404, 422, …) → non-retryable validation error.
  return {
    kind: 'validation',
    status: 'failed',
    retryable: false,
    stopLoop: false,
    message: getErrorMessage(error, 'La venta fue rechazada por el servidor (datos inválidos).'),
  };
}

// ── Eligibility ───────────────────────────────────────────────────────────────

/**
 * Whether a queued sale should be picked up by the sync engine. Only `pending`
 * sales and `failed` sales still marked retryable are eligible. `syncing`,
 * `synced` and `conflict` are excluded.
 */
export function isSyncableSale(item: OfflineSaleQueueItem): boolean {
  const eligibleStatus =
    item.status === 'pending' || (item.status === 'failed' && item.retryable !== false);
  if (!eligibleStatus) return false;
  if (!item.client_order_id) return false;
  if (!item.sale_payload?.items?.length) return false;
  if (!item.sale_payload?.payments?.length) return false;
  const total = Number.parseFloat(item.totals_snapshot?.total ?? '0');
  return Number.isFinite(total) && total > 0;
}

// ── Engine ────────────────────────────────────────────────────────────────────

let syncInFlight = false;

/** Resets the in-flight guard. Intended for tests only. */
export function __resetSyncInFlightForTests(): void {
  syncInFlight = false;
}

export interface SyncOptions {
  storage?: OfflineSalesStorage;
  submit: OfflineSaleSubmit;
  isOnline: boolean;
  /** Injectable clock for deterministic `synced_at`/`updated_at`. */
  now?: () => string;
}

const EMPTY_RESULT: SyncRunResult = {
  ran: false,
  attempted: 0,
  synced: 0,
  failed: 0,
  conflicts: 0,
  stoppedOnError: false,
};

/**
 * Drains the offline sale queue. Returns a summary of the run. Safe to call
 * repeatedly: it no-ops while offline or when another run is already active.
 */
export async function syncOfflineSales(options: SyncOptions): Promise<SyncRunResult> {
  const { submit, isOnline } = options;
  const storage = options.storage ?? getOfflineSalesStorage();
  const clock = options.now ?? (() => new Date().toISOString());

  if (!isOnline) return { ...EMPTY_RESULT };
  if (syncInFlight) return { ...EMPTY_RESULT };

  syncInFlight = true;
  const result: SyncRunResult = { ...EMPTY_RESULT, ran: true };

  try {
    const all = await storage.list();
    const queue = all
      .filter(isSyncableSale)
      .sort((a, b) => a.created_at.localeCompare(b.created_at));

    for (const sale of queue) {
      result.attempted += 1;

      // Mark as syncing so the UI reflects in-progress state.
      await storage.put({ ...sale, status: 'syncing', updated_at: clock() });

      try {
        const response = await submit(sale.sale_payload);
        await storage.put({
          ...sale,
          status: 'synced',
          server_id: response.server_id,
          synced_at: clock(),
          updated_at: clock(),
          duplicate_ack: response.duplicate === true,
          last_error: null,
          retryable: false,
        });
        result.synced += 1;
      } catch (error) {
        const classification = classifySyncError(error);
        await storage.put({
          ...sale,
          status: classification.status,
          retryable: classification.retryable,
          sync_attempts: sale.sync_attempts + 1,
          last_error: classification.message,
          updated_at: clock(),
        });

        if (classification.status === 'conflict') {
          result.conflicts += 1;
        } else if (classification.status === 'failed') {
          result.failed += 1;
        }

        if (classification.stopLoop) {
          result.stoppedOnError = true;
          break;
        }
      }
    }

    return result;
  } finally {
    syncInFlight = false;
  }
}
