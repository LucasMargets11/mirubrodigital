/**
 * Validation + construction of offline POS sales (PR-OFF-04).
 *
 * Pure helpers (no React, no IndexedDB) so they can be unit-tested directly and
 * reused by the capture hook. They enforce the offline business rules from the
 * snapshot and assemble a backend-compatible {@link OfflineSaleQueueItem}.
 */

import type { CartItem } from '../components/SaleItemsPanel';
import type { StoredPosOfflineBootstrap } from './types';
import { generateClientOrderId } from './offline-sale-id';
import {
  evaluateSnapshotExpiry,
  isAtPendingLimit,
  PENDING_LIMIT_MESSAGE,
  SNAPSHOT_EXPIRED_MESSAGE,
} from './offline-snapshot-policy';
import type {
  OfflinePaymentMethodCode,
  OfflineSalePayload,
  OfflineSalePaymentSnapshot,
  OfflineSaleQueueItem,
  OfflineSaleTotals,
} from './offline-sales-types';

/** Payment methods accepted for offline capture (snapshot static list). */
export const OFFLINE_PAYMENT_METHODS: readonly OfflinePaymentMethodCode[] = [
  'cash',
  'transfer',
  'card',
  'other',
] as const;

export const OFFLINE_PAYMENT_LABELS: Record<OfflinePaymentMethodCode, string> = {
  cash: 'Efectivo',
  transfer: 'Transferencia',
  card: 'Tarjeta',
  other: 'Otro',
};

export interface OfflineSaleEmployee {
  id: string;
  code: string;
}

export interface OfflineSaleInput {
  snapshot: StoredPosOfflineBootstrap | null;
  cart: CartItem[];
  paymentMethod: OfflinePaymentMethodCode;
  employee: OfflineSaleEmployee;
  note?: string;
  /**
   * Client clock (ISO) for the snapshot-expiry check. When omitted, expiry is
   * not enforced (kept optional so legacy/pure callers stay backwards-compatible).
   */
  now?: string;
  /**
   * Number of unsynced sales already queued locally, for the pending-limit
   * check. When omitted, the limit is not enforced.
   */
  unsyncedCount?: number;
}

export type OfflineSaleValidation =
  | { ok: true }
  | { ok: false; message: string };

/** Sum of price × quantity across the cart, as a number. */
export function cartTotal(cart: CartItem[]): number {
  return cart.reduce(
    (sum, item) => sum + parseFloat(item.product.price) * item.quantity,
    0,
  );
}

/**
 * Validates whether an offline quick-sale may be captured from the snapshot.
 * Returns a human-readable message on the first failing rule.
 */
export function validateOfflineSale(input: OfflineSaleInput): OfflineSaleValidation {
  const { snapshot, cart, paymentMethod } = input;

  if (!snapshot) {
    return {
      ok: false,
      message:
        'No hay datos offline descargados. Conectate a Internet y actualizá datos offline.',
    };
  }
  if (!snapshot.offline_policy.enabled) {
    return { ok: false, message: 'Modo offline no habilitado para este negocio.' };
  }
  if (snapshot.offline_policy.mode !== 'quick_sale_only') {
    return {
      ok: false,
      message: 'El modo offline solo admite venta rápida en esta versión.',
    };
  }
  if (!snapshot.operation_settings.pos_quick_sale_enabled) {
    return {
      ok: false,
      message: 'La venta rápida no está habilitada para este negocio.',
    };
  }
  // PR-OFF-07: do not operate on stale offline data. Checked before the cash
  // and stock rules so we never assume the snapshot (incl. its cash session) is
  // still valid once the data has expired.
  if (input.now !== undefined) {
    const expiry = evaluateSnapshotExpiry(snapshot, new Date(input.now));
    if (expiry.isExpired) {
      return { ok: false, message: SNAPSHOT_EXPIRED_MESSAGE };
    }
  }
  // PR-OFF-07: cap the local queue so it cannot grow unbounded while offline.
  if (input.unsyncedCount !== undefined && isAtPendingLimit(input.unsyncedCount)) {
    return { ok: false, message: PENDING_LIMIT_MESSAGE };
  }
  if (cart.length === 0) {
    return { ok: false, message: 'Agregá al menos un producto.' };
  }
  if (!OFFLINE_PAYMENT_METHODS.includes(paymentMethod)) {
    return { ok: false, message: 'Método de pago no disponible en modo offline.' };
  }
  if (snapshot.commercial_settings.require_customer_for_sales) {
    return {
      ok: false,
      message:
        'Este negocio requiere cliente para vender. La venta offline no está disponible con esta configuración.',
    };
  }
  if (
    snapshot.commercial_settings.block_sales_if_no_open_cash_session &&
    snapshot.cash_session == null
  ) {
    return {
      ok: false,
      message:
        'No hay caja abierta en el snapshot offline. Abrí caja y actualizá datos offline antes de operar sin conexión.',
    };
  }

  if (!snapshot.commercial_settings.allow_sell_without_stock) {
    for (const item of cart) {
      const snapshotProduct = snapshot.products.find((p) => p.id === item.product.id);
      const available = snapshotProduct
        ? parseFloat(snapshotProduct.current_stock)
        : 0;
      if (!Number.isFinite(available) || available < item.quantity) {
        return {
          ok: false,
          message: `No hay stock suficiente en el snapshot para «${item.product.name}». Actualizá datos offline o ajustá la cantidad.`,
        };
      }
    }
  }

  return { ok: true };
}

/**
 * Builds a queued offline sale item from validated input. Does NOT validate —
 * call {@link validateOfflineSale} first.
 *
 * `now` and `clientOrderId` are injectable for deterministic tests.
 */
export function buildOfflineSale(
  input: OfflineSaleInput,
  options: { now?: string; clientOrderId?: string; localId?: string } = {},
): OfflineSaleQueueItem {
  const snapshot = input.snapshot!;
  const now = options.now ?? new Date().toISOString();
  const clientOrderId = options.clientOrderId ?? generateClientOrderId();
  const localId = options.localId ?? generateClientOrderId();

  const total = cartTotal(input.cart);
  const itemCount = input.cart.reduce((sum, i) => sum + i.quantity, 0);

  const items = input.cart.map((item) => ({
    product: item.product.id,
    quantity: String(item.quantity),
    unit_price: item.product.price,
  }));

  const payments: OfflineSalePayload['payments'] = [
    { method: input.paymentMethod, amount: total.toFixed(2) },
  ];

  const sale_payload: OfflineSalePayload = {
    client_order_id: clientOrderId,
    items,
    payments,
    note: input.note?.trim() || 'Venta offline',
    source: 'pos_offline',
  };

  const totals_snapshot: OfflineSaleTotals = {
    subtotal: total.toFixed(2),
    discount: '0.00',
    total: total.toFixed(2),
    item_count: itemCount,
  };

  const payment_snapshot: OfflineSalePaymentSnapshot[] = [
    { method: input.paymentMethod, amount: total.toFixed(2) },
  ];

  return {
    local_id: localId,
    client_order_id: clientOrderId,
    business_id: snapshot.business.id,
    employee_id: input.employee.id,
    employee_code: input.employee.code,
    cash_session_id: snapshot.cash_session?.id ?? null,
    created_at: now,
    updated_at: now,
    status: 'pending',
    sync_attempts: 0,
    last_error: null,
    retryable: true,
    server_id: null,
    synced_at: null,
    duplicate_ack: false,
    sale_payload,
    totals_snapshot,
    payment_snapshot,
    source: 'pos_offline',
    offline_snapshot_generated_at: snapshot.generated_at,
    offline_snapshot_saved_at: snapshot.saved_at,
  };
}
