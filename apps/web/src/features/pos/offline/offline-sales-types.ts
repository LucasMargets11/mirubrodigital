/**
 * Types for the offline POS sale queue (PR-OFF-04).
 *
 * An offline sale is captured locally and persisted in IndexedDB as a pending
 * item. It is NOT sent to the backend in this PR — syncing arrives in
 * PR-OFF-05. The `sale_payload` is shaped to be forward-compatible with
 * POST /api/v1/pos/sales/ so the future sync engine can submit it as-is.
 */

/** Offline payment methods allowed by the snapshot (PR-OFF-02A static list). */
export type OfflinePaymentMethodCode = 'cash' | 'transfer' | 'card' | 'other';

export type OfflineSaleStatus =
  | 'pending'
  | 'syncing'
  | 'synced'
  | 'failed'
  | 'conflict';

/** Single line item in the offline sale payload. */
export interface OfflineSalePayloadItem {
  /** Product UUID (snapshot product id). */
  product: string;
  /** Decimal string quantity, e.g. "1". */
  quantity: string;
  /** Decimal string unit price captured from the snapshot, e.g. "6500.00". */
  unit_price: string;
}

/** Single payment in the offline sale payload. */
export interface OfflineSalePayloadPayment {
  method: OfflinePaymentMethodCode;
  /** Decimal string amount, e.g. "6500.00". */
  amount: string;
}

/**
 * Backend-compatible sale payload. Mirrors what POST /api/v1/pos/sales/ will
 * accept once sync is implemented. `client_order_id` is the idempotency key.
 */
export interface OfflineSalePayload {
  client_order_id: string;
  items: OfflineSalePayloadItem[];
  payments: OfflineSalePayloadPayment[];
  note: string;
  source: 'pos_offline';
}

/** Captured totals for display + reconciliation (local only). */
export interface OfflineSaleTotals {
  subtotal: string;
  discount: string;
  total: string;
  item_count: number;
}

/** Captured payment summary for display (local only). */
export interface OfflineSalePaymentSnapshot {
  method: OfflinePaymentMethodCode;
  amount: string;
}

/**
 * A single queued offline sale persisted in IndexedDB.
 */
export interface OfflineSaleQueueItem {
  /** Local primary key (also a UUID, distinct from client_order_id). */
  local_id: string;
  /** Backend idempotency key — the canonical sale identity. */
  client_order_id: string;
  business_id: string;
  employee_id: string;
  employee_code: string;
  /** Cash session id from the snapshot, or null when none was open. */
  cash_session_id: string | null;
  created_at: string;
  updated_at: string;
  status: OfflineSaleStatus;
  sync_attempts: number;
  last_error: string | null;
  /**
   * Whether a `failed` sale may be retried by the sync engine. `true` for
   * network/server (transient) failures, `false` for validation (400) errors.
   * `pending` sales are always retryable; `conflict`/`synced` are terminal.
   */
  retryable: boolean;
  /** Server-assigned Sale id once synced (PR-OFF-05). Null until synced. */
  server_id: string | null;
  /** ISO timestamp when the sale was confirmed synced. Null until synced. */
  synced_at: string | null;
  /**
   * True when the server confirmed this sale already existed (idempotent
   * duplicate ack) rather than creating it fresh.
   */
  duplicate_ack: boolean;
  sale_payload: OfflineSalePayload;
  totals_snapshot: OfflineSaleTotals;
  payment_snapshot: OfflineSalePaymentSnapshot[];
  source: 'pos_offline';
  /** Provenance of the snapshot the sale was built from. */
  offline_snapshot_generated_at: string;
  offline_snapshot_saved_at: string;
}

/**
 * Result returned by POST /api/v1/pos/sales/ when syncing an offline sale.
 * The backend uses `client_order_id` for idempotency: `duplicate` is true when
 * the sale already existed server-side.
 */
export interface OfflineSaleSyncResult {
  sale: { id: string };
  duplicate: boolean;
  server_id: string;
}
