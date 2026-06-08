/**
 * Offline snapshot safety policy (PR-OFF-07).
 *
 * Pure helpers (no React, no IndexedDB) that enforce the operational guardrails
 * for the POS offline MVP:
 *  - snapshot expiry (offline_policy.expires_in_hours)
 *  - "expiring soon" warning window
 *  - maximum number of unsynced offline sales allowed in the local queue
 *
 * Keeping these decoupled lets the validation layer, the capture hook and the
 * UI all share one source of truth, and makes the rules unit-testable.
 */

import type { OfflineSaleQueueItem } from './offline-sales-types';
import type { StoredPosOfflineBootstrap } from './types';

/** Hours-before-expiry threshold under which we warn the operator. */
export const SNAPSHOT_EXPIRY_WARNING_HOURS = 2;

/**
 * Maximum number of unsynced offline sales (pending + syncing + failed +
 * conflict) allowed before new offline sales are blocked. Synced sales never
 * count — they already live in the backend.
 */
export const MAX_PENDING_OFFLINE_SALES = 50;

// ── User-facing messages (verbatim, reused by UI + validation) ───────────────

export const SNAPSHOT_EXPIRED_MESSAGE =
  'Los datos offline están vencidos. Conectate a Internet y actualizá datos offline.';

export const SNAPSHOT_EXPIRING_SOON_MESSAGE =
  'Los datos offline están por vencer. Actualizalos cuando tengas conexión.';

export const PENDING_LIMIT_MESSAGE =
  'Hay demasiadas ventas pendientes. Conectate a Internet y sincronizá antes de seguir.';

// ── Snapshot expiry ──────────────────────────────────────────────────────────

export interface SnapshotExpiry {
  /** ISO timestamp at which the snapshot expires, or null if undeterminable. */
  expiresAt: string | null;
  /** True when the snapshot is past its expiry (or has an invalid timestamp). */
  isExpired: boolean;
  /** True when it is not yet expired but within the warning window. */
  isExpiringSoon: boolean;
  /** Whole hours remaining until expiry (floored, min 0), or null. */
  hoursUntilExpiry: number | null;
}

/**
 * Evaluates a snapshot's freshness against `offline_policy.expires_in_hours`,
 * measured from the server `generated_at` timestamp. A snapshot with an invalid
 * or missing timestamp is treated as expired (fail-safe).
 */
export function evaluateSnapshotExpiry(
  snapshot: StoredPosOfflineBootstrap | null,
  now: Date = new Date(),
): SnapshotExpiry {
  if (!snapshot) {
    return { expiresAt: null, isExpired: true, isExpiringSoon: false, hoursUntilExpiry: null };
  }

  const generated = new Date(snapshot.generated_at);
  const expiresInHours = snapshot.offline_policy.expires_in_hours;
  if (Number.isNaN(generated.getTime()) || !Number.isFinite(expiresInHours)) {
    return { expiresAt: null, isExpired: true, isExpiringSoon: false, hoursUntilExpiry: null };
  }

  const expiresMs = generated.getTime() + expiresInHours * 60 * 60 * 1000;
  const msLeft = expiresMs - now.getTime();
  const isExpired = msLeft <= 0;
  const hoursLeftRaw = msLeft / (60 * 60 * 1000);
  const hoursUntilExpiry = isExpired ? 0 : Math.floor(hoursLeftRaw);
  const isExpiringSoon = !isExpired && hoursLeftRaw <= SNAPSHOT_EXPIRY_WARNING_HOURS;

  return {
    expiresAt: new Date(expiresMs).toISOString(),
    isExpired,
    isExpiringSoon,
    hoursUntilExpiry,
  };
}

// ── Pending-queue limit ──────────────────────────────────────────────────────

/**
 * Counts unsynced offline sales (everything except `synced`). These are the
 * sales that still occupy the local queue and count toward the pending limit.
 */
export function countUnsyncedOfflineSales(sales: OfflineSaleQueueItem[]): number {
  return sales.filter((s) => s.status !== 'synced').length;
}

/** True when the unsynced queue has reached the configured maximum. */
export function isAtPendingLimit(unsyncedCount: number): boolean {
  return unsyncedCount >= MAX_PENDING_OFFLINE_SALES;
}
