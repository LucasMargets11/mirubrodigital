'use client';

/**
 * POS-safe operation settings (PR-OFF-10).
 *
 * The POS runs under an *employee operative* session, which is NOT authorized
 * to read the owner/admin endpoint `/api/v1/resto/settings/operation/`. Calling
 * `useRestaurantOperationSettings()` from inside `/pos/*` produced repeated
 * `401 Unauthorized` responses and console noise.
 *
 * Instead we derive the operation flags the POS actually needs (quick sale /
 * kitchen / counter orders) from the POS offline bootstrap snapshot, which is
 * fetched with the employee token (POS-authenticated) and persisted locally in
 * IndexedDB. Reading the snapshot works both online and offline and never hits
 * an owner/admin endpoint.
 *
 * When no snapshot is available yet we fall back to safe defaults so quick sale
 * always works and kitchen stays available when the business has it on.
 *
 * NOTE: `default_pos_mode` is not part of the POS bootstrap payload, so it
 * always resolves to the safe default (`quick_sale`). The cashier can still
 * switch to kitchen mode manually when it is enabled. This matches the previous
 * online behaviour, where the 401 made the POS fall back to the same defaults.
 */

import { useMemo } from 'react';

import {
  DEFAULT_RESTAURANT_OPERATION_SETTINGS,
  type RestaurantOperationSettings,
} from '@/features/resto/types';

import { usePosOfflineSnapshot } from './bootstrap-hooks';
import type { OfflineOperationSettings } from './types';

/**
 * Maps a POS bootstrap snapshot's `operation_settings` into the shape the POS
 * UI consumes. Returns safe defaults when there is no snapshot.
 */
export function posOperationSettingsFromSnapshot(
  operationSettings: OfflineOperationSettings | null | undefined,
): RestaurantOperationSettings {
  if (!operationSettings) {
    return DEFAULT_RESTAURANT_OPERATION_SETTINGS;
  }
  return {
    ...DEFAULT_RESTAURANT_OPERATION_SETTINGS,
    pos_quick_sale_enabled: operationSettings.pos_quick_sale_enabled,
    kitchen_enabled: operationSettings.kitchen_enabled,
    tables_enabled: operationSettings.tables_enabled,
    counter_orders_enabled: operationSettings.counter_orders_enabled,
    // Not present in the POS bootstrap payload — keep the safe default.
    default_pos_mode: 'quick_sale',
  };
}

/**
 * POS-authenticated operation settings. Reads the locally-persisted offline
 * snapshot (IndexedDB) instead of the owner/admin settings endpoint, so it is
 * safe to use anywhere under `/pos/*` without triggering 401s.
 */
export function usePosOperationSettings(): RestaurantOperationSettings {
  const snapshotQuery = usePosOfflineSnapshot();
  const operationSettings = snapshotQuery.data?.operation_settings ?? null;
  return useMemo(
    () => posOperationSettingsFromSnapshot(operationSettings),
    [operationSettings],
  );
}
