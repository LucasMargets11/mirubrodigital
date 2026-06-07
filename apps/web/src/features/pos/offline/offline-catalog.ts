'use client';

/**
 * Offline catalog source for the POS quick-sale screen (PR-OFF-03).
 *
 * When the device is offline this exposes products / categories / payment
 * methods read from the locally-persisted bootstrap snapshot (PR-OFF-02B),
 * mapped into the same shapes the online catalog uses (`PosProduct`,
 * `PosCategory`) so the existing cart/UI primitives can be reused.
 *
 * This is read-only contingency data. It does NOT enable offline sales: the
 * caller is responsible for blocking sale confirmation while offline.
 */

import { useMemo } from 'react';
import type { PosCategory, PosProduct } from '@/types/pos-cash';
import { useNetworkStatus } from '@/hooks/use-network-status';
import { usePosOfflineSnapshot } from './bootstrap-hooks';
import type {
  OfflineCategory,
  OfflinePaymentMethod,
  OfflineProduct,
  StoredPosOfflineBootstrap,
} from './types';

export type OfflineCatalogStatus =
  /** Device is online — use the regular online catalog flow. */
  | 'online'
  /** Offline, snapshot still loading from IndexedDB. */
  | 'loading'
  /** Offline, business has offline mode disabled in the snapshot policy. */
  | 'offline-disabled'
  /** Offline, no snapshot has ever been downloaded. */
  | 'offline-no-snapshot'
  /** Offline, a valid snapshot is available for browsing. */
  | 'offline-ready';

export interface PosOfflineCatalog {
  /** True when the browser reports no connection. */
  isOffline: boolean;
  status: OfflineCatalogStatus;
  snapshot: StoredPosOfflineBootstrap | null;
  /** ISO timestamp of when the snapshot was saved locally, or null. */
  savedAt: string | null;
  /** Active products mapped to the online `PosProduct` shape. */
  products: PosProduct[];
  /** Active categories mapped to the online `PosCategory` shape. */
  categories: PosCategory[];
  paymentMethods: OfflinePaymentMethod[];
  /**
   * True only when the offline catalog may be used to build a cart:
   * offline + valid snapshot + policy enabled + quick sale enabled.
   */
  canBuildCart: boolean;
}

/** Maps a snapshot product to the online `PosProduct` shape. */
export function offlineProductToPosProduct(p: OfflineProduct): PosProduct {
  return {
    id: p.id,
    name: p.name,
    sku: p.sku,
    price: p.price,
    stock_quantity: p.current_stock,
    stock_min: p.stock_min,
    category_id: p.category_id,
    is_active: p.is_active,
  };
}

/**
 * Builds the online `PosCategory[]` from a snapshot, counting only active
 * products per active category.
 */
export function buildOfflineCategories(
  categories: OfflineCategory[],
  activeProducts: OfflineProduct[],
): PosCategory[] {
  return categories
    .filter((c) => c.is_active)
    .map((c) => ({
      id: c.id,
      name: c.name,
      products_count: activeProducts.filter((p) => p.category_id === c.id).length,
    }));
}

/** Formats a saved-at ISO timestamp as a short HH:mm local time. */
export function formatSavedAtTime(savedAt: string): string {
  const date = new Date(savedAt);
  if (Number.isNaN(date.getTime())) {
    return savedAt;
  }
  return new Intl.DateTimeFormat('es-AR', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

/**
 * Resolves the catalog source based on connectivity + the local snapshot.
 */
export function usePosOfflineCatalog(): PosOfflineCatalog {
  const { isOffline } = useNetworkStatus();
  const snapshotQuery = usePosOfflineSnapshot();
  const snapshot = snapshotQuery.data ?? null;

  const status = useMemo<OfflineCatalogStatus>(() => {
    if (!isOffline) return 'online';
    if (snapshotQuery.isLoading) return 'loading';
    if (!snapshot) return 'offline-no-snapshot';
    if (!snapshot.offline_policy.enabled) return 'offline-disabled';
    return 'offline-ready';
  }, [isOffline, snapshotQuery.isLoading, snapshot]);

  const activeProducts = useMemo(
    () => (snapshot ? snapshot.products.filter((p) => p.is_active) : []),
    [snapshot],
  );

  const products = useMemo(
    () => activeProducts.map(offlineProductToPosProduct),
    [activeProducts],
  );

  const categories = useMemo(
    () => (snapshot ? buildOfflineCategories(snapshot.categories, activeProducts) : []),
    [snapshot, activeProducts],
  );

  const canBuildCart =
    status === 'offline-ready' &&
    snapshot !== null &&
    snapshot.operation_settings.pos_quick_sale_enabled;

  return {
    isOffline,
    status,
    snapshot,
    savedAt: snapshot?.saved_at ?? null,
    products,
    categories,
    paymentMethods: snapshot?.payment_methods ?? [],
    canBuildCart,
  };
}
