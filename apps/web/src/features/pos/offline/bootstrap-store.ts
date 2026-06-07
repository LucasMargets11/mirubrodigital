/**
 * Bootstrap store — orchestration over the IndexedDB persistence layer
 * (PR-OFF-02B).
 *
 * Responsibilities:
 * - Build the locally-stored snapshot from a server payload (adds `saved_at`).
 * - Save (atomic full replacement), load and clear the snapshot.
 *
 * Failure contract: `saveBootstrapSnapshot` performs an atomic replace at the
 * storage layer. If the save rejects, the previous snapshot is left untouched
 * (callers must not clear on error). This is what keeps the last-good snapshot
 * available when a refresh download fails.
 *
 * NOTE: this PR persists data only. It does NOT enable offline sales.
 */

import { getBootstrapStorage, type BootstrapStorage } from './db';
import type { PosOfflineBootstrapPayload, StoredPosOfflineBootstrap } from './types';

/**
 * Wraps a server payload into the locally-stored shape by stamping `saved_at`.
 */
export function buildStoredSnapshot(
  payload: PosOfflineBootstrapPayload,
  savedAt: string = new Date().toISOString(),
): StoredPosOfflineBootstrap {
  return { ...payload, saved_at: savedAt };
}

/**
 * Persists a fresh bootstrap payload, fully replacing any previous snapshot.
 * Returns the stored snapshot (with `saved_at`).
 *
 * On storage failure this rejects WITHOUT having mutated the existing snapshot,
 * so a failed refresh keeps the last-good data intact.
 */
export async function saveBootstrapSnapshot(
  payload: PosOfflineBootstrapPayload,
  storage: BootstrapStorage = getBootstrapStorage(),
): Promise<StoredPosOfflineBootstrap> {
  const snapshot = buildStoredSnapshot(payload);
  await storage.save(snapshot);
  return snapshot;
}

/**
 * Loads the persisted snapshot, or null when nothing has been downloaded yet.
 */
export function loadBootstrapSnapshot(
  storage: BootstrapStorage = getBootstrapStorage(),
): Promise<StoredPosOfflineBootstrap | null> {
  return storage.load();
}

/**
 * Removes the persisted snapshot.
 */
export function clearBootstrapSnapshot(
  storage: BootstrapStorage = getBootstrapStorage(),
): Promise<void> {
  return storage.clear();
}
