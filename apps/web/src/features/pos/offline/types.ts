/**
 * Types for the POS offline bootstrap snapshot (PR-OFF-02B).
 *
 * These mirror the backend payload returned by
 *   GET /api/v1/pos/offline/bootstrap/   (PR-OFF-02A)
 *
 * This is the read-only contingency snapshot. It NEVER contains tokens, PINs,
 * passwords, customers, sales, payments, orders, tables or kitchen state.
 */

export interface OfflineBusiness {
  id: string;
  name: string;
  currency: string;
  default_service: string;
  timezone: string;
}

export interface OfflineEmployee {
  id: string;
  name: string;
  role: string;
  code: string;
}

export type OfflinePolicyMode = 'quick_sale_only';

export interface OfflinePolicy {
  enabled: boolean;
  mode: OfflinePolicyMode;
  expires_in_hours: number;
  supports_kitchen: boolean;
  supports_tables: boolean;
  supports_orders: boolean;
}

export interface OfflineCommercialSettings {
  allow_sell_without_stock: boolean;
  block_sales_if_no_open_cash_session: boolean;
  require_customer_for_sales: boolean;
}

export interface OfflineOperationSettings {
  pos_quick_sale_enabled: boolean;
  kitchen_enabled: boolean;
  tables_enabled: boolean;
  counter_orders_enabled: boolean;
}

export interface OfflineCashSession {
  id: string;
  status: string;
  opened_at: string | null;
  register_name: string | null;
}

export interface OfflineCategory {
  id: string;
  name: string;
  is_active: boolean;
}

export interface OfflineProduct {
  id: string;
  name: string;
  sku: string;
  barcode: string;
  category_id: string | null;
  price: string;
  stock_min: string;
  current_stock: string;
  is_active: boolean;
}

export interface OfflinePaymentMethod {
  code: string;
  label: string;
}

/**
 * Raw payload as returned by the backend bootstrap endpoint.
 */
export interface PosOfflineBootstrapPayload {
  bootstrap_version: number;
  generated_at: string;
  business: OfflineBusiness;
  employee: OfflineEmployee;
  offline_policy: OfflinePolicy;
  commercial_settings: OfflineCommercialSettings;
  operation_settings: OfflineOperationSettings;
  cash_session: OfflineCashSession | null;
  categories: OfflineCategory[];
  products: OfflineProduct[];
  payment_methods: OfflinePaymentMethod[];
}

/**
 * Locally-persisted snapshot. Adds `saved_at` (client clock) on top of the
 * server payload so the UI can show when the data was last refreshed.
 */
export interface StoredPosOfflineBootstrap extends PosOfflineBootstrapPayload {
  saved_at: string;
}
