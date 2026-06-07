'use client';

/**
 * usePosOfflineGuard (PR-OFF-07)
 *
 * Derives the operational guardrails for the POS offline MVP from the local
 * snapshot + the offline sale queue:
 *  - snapshot expiry / "expiring soon" state
 *  - unsynced queue size vs the pending limit
 *  - a single `blockReason` (non-null ⇒ new offline sales are blocked)
 *  - a single non-blocking `warningMessage`
 *
 * Consumed by PosNewSalePage (to gate confirmation + show messages), by the
 * contingency notice and the connection banner. The authoritative enforcement
 * still happens at capture time (see usePosCaptureOfflineSale).
 */

import { useMemo } from 'react';

import { usePosOfflineSales } from './offline-sales-hooks';
import { usePosOfflineCatalog } from './offline-catalog';
import {
  countUnsyncedOfflineSales,
  evaluateSnapshotExpiry,
  isAtPendingLimit,
  PENDING_LIMIT_MESSAGE,
  SNAPSHOT_EXPIRED_MESSAGE,
  SNAPSHOT_EXPIRING_SOON_MESSAGE,
  type SnapshotExpiry,
} from './offline-snapshot-policy';
import type { StoredPosOfflineBootstrap } from './types';

export interface PosOfflineGuard {
  isOffline: boolean;
  snapshot: StoredPosOfflineBootstrap | null;
  /** When the snapshot was saved locally (ISO), or null. */
  savedAt: string | null;
  expiry: SnapshotExpiry;
  unsyncedCount: number;
  atPendingLimit: boolean;
  /** Reason new offline sales are blocked, or null when allowed. */
  blockReason: string | null;
  /** Non-blocking advisory (e.g. "expiring soon"), or null. */
  warningMessage: string | null;
}

/**
 * Computes the offline guardrail state. `expiry` is evaluated against the
 * current clock at render time (snapshot/queue are otherwise stable inputs).
 */
export function usePosOfflineGuard(): PosOfflineGuard {
  const catalog = usePosOfflineCatalog();
  const { data } = usePosOfflineSales();

  const snapshot = catalog.snapshot;
  const unsyncedCount = useMemo(() => countUnsyncedOfflineSales(data ?? []), [data]);

  // Evaluate expiry on every render so the state reflects the passage of time.
  const expiry = evaluateSnapshotExpiry(snapshot);
  const atPendingLimit = isAtPendingLimit(unsyncedCount);

  const blockReason = (() => {
    if (!snapshot) return null;
    if (expiry.isExpired) return SNAPSHOT_EXPIRED_MESSAGE;
    if (atPendingLimit) return PENDING_LIMIT_MESSAGE;
    return null;
  })();

  const warningMessage =
    snapshot && !expiry.isExpired && expiry.isExpiringSoon
      ? SNAPSHOT_EXPIRING_SOON_MESSAGE
      : null;

  return {
    isOffline: catalog.isOffline,
    snapshot,
    savedAt: catalog.savedAt,
    expiry,
    unsyncedCount,
    atPendingLimit,
    blockReason,
    warningMessage,
  };
}
