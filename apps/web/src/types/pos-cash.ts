/**
 * TypeScript types for the POS operative cash endpoints.
 *
 * These types match the backend POS serializers (cash/pos_serializers.py) and
 * are intentionally separate from the admin cash types in features/cash/types.ts
 * to avoid coupling the two auth domains.
 *
 * All string decimals come as-is from the DRF DecimalField serializer.
 */

// ── Employee summary embedded in session responses ────────────────────────────

export interface PosEmployeeSummary {
  id: string;
  employee_code: string;
  display_name: string;
}

// ── Session totals ────────────────────────────────────────────────────────────

export interface PosCashSessionTotals {
  total_sales: string;
  total_in: string;
  total_out: string;
  cash_expected_total: string;
  cash_in_from_sales: string;
}

// ── Cash session ──────────────────────────────────────────────────────────────

export interface PosCashSession {
  id: string;
  /** Lowercase values as stored in DB: 'open' | 'closed' | 'audited' */
  status: 'open' | 'closed' | 'audited';
  opening_cash_amount: string;
  closing_cash_counted: string | null;
  expected_cash_total: string | null;
  difference_amount: string | null;
  closing_note: string;
  opened_by_name: string;
  opened_at: string; // ISO 8601
  closed_at: string | null;
  opened_by_employee: PosEmployeeSummary | null;
  totals: PosCashSessionTotals;
}

/** Wrapper returned by GET /pos/cash/current/, POST /pos/cash/open/, POST /pos/cash/current/close/ */
export interface PosCashSessionResponse {
  session: PosCashSession | null;
}

// ── Request payloads ──────────────────────────────────────────────────────────

/** POST /api/v1/pos/cash/open/ */
export interface PosCashOpenRequest {
  /** Decimal string, e.g. "500.00". Default "0.00" if omitted. */
  opening_cash_amount?: string;
  /** UUID of an existing CashRegister in this business. Optional. */
  register_id?: string | null;
}

/** POST /api/v1/pos/cash/current/close/ */
export interface PosCashCloseRequest {
  /** Decimal string. If omitted, difference_amount stays null. */
  closing_cash_counted?: string | null;
  closing_note?: string;
}

export type PosCashMovementType = 'in' | 'out';
export type PosCashMovementCategory = 'expense' | 'withdraw' | 'deposit' | 'other';
export type PosCashMovementMethod = 'cash' | 'debit' | 'credit' | 'transfer' | 'wallet' | 'account';

/** POST /api/v1/pos/cash/current/movements/ */
export interface PosCashMovementRequest {
  movement_type: PosCashMovementType;
  category?: PosCashMovementCategory;
  method?: PosCashMovementMethod;
  /** Decimal string, e.g. "200.00". Minimum "0.01". */
  amount: string;
  note?: string;
}

// ── Response for movement creation ───────────────────────────────────────────

export interface PosCashMovement {
  id: string;
  movement_type: PosCashMovementType;
  category: PosCashMovementCategory;
  method: PosCashMovementMethod;
  amount: string;
  note: string;
  created_at: string;
  session_id: string;
}

/** Wrapper returned by POST /pos/cash/current/movements/ */
export interface PosCashMovementResponse {
  movement: PosCashMovement;
}

/** Wrapper returned by GET /pos/cash/current/movements/ */
export interface PosCashCurrentMovementsResponse {
  movements: PosCashMovement[];
  session_id: string | null;
}

// ── POS Catalog — product search ──────────────────────────────────────────────

/** Minimal product record returned by GET /api/v1/pos/catalog/products/ */
export interface PosProduct {
  id: string;
  name: string;
  sku: string;
  /** Decimal string, e.g. "150.00" */
  price: string;
  /** Decimal string, e.g. "12.00" */
  stock_quantity: string;
  /** Decimal string — minimum stock threshold for low-stock warning */
  stock_min: string;
  /** UUID of the category, or null when uncategorised */
  category_id: string | null;
  is_active: boolean;
}

export interface PosProductsResponse {
  results: PosProduct[];
  count: number;
}

// ── POS Catalog — categories ──────────────────────────────────────────────────

/** Category record returned by GET /api/v1/pos/catalog/categories/ */
export interface PosCategory {
  id: string;
  name: string;
  /** Count of active products in this category */
  products_count: number;
}

export interface PosCategoriesResponse {
  results: PosCategory[];
  count: number;
}

// ── POS Sales — create sale ───────────────────────────────────────────────────

export interface PosSaleItemPayload {
  product_id: string;
  quantity: number;
  /** Decimal string when provided, e.g. "150.00" */
  unit_price?: string;
}

/** A single payment line in a split-payment sale. */
export interface PosSalePaymentLine {
  /** Payment method matching cash.Payment.Method choices */
  method: 'cash' | 'debit' | 'credit' | 'transfer' | 'wallet' | 'account';
  /** Decimal string, e.g. "10000.00" */
  amount: string;
  /** Optional reference/note for this payment line */
  reference?: string;
}

/**
 * Request body for POST /api/v1/pos/sales/
 * Note: cash_session_id is intentionally absent — the server auto-assigns
 * the employee's current open session.
 *
 * Supports two modes:
 * - Legacy: send `payment_method` (single payment, backward compat)
 * - Split: send `payments` array (multiple payment lines)
 */
export interface PosSalePayload {
  payment_method?: 'cash' | 'transfer' | 'card' | 'other';
  items: PosSaleItemPayload[];
  payments?: PosSalePaymentLine[];
  customer_id?: string | null;
  discount?: number;
  notes?: string;
}

// ── POS Customers ─────────────────────────────────────────────────────────────

/** Minimal customer record returned by GET /api/v1/pos/customers/?search= */
export interface PosCustomerSummary {
  id: string;
  name: string;
  doc_type: string;
  doc_number: string;
  email: string;
  phone: string;
}

export interface PosCustomersResponse {
  results: PosCustomerSummary[];
  count: number;
}

export interface PosCustomerCreatePayload {
  name: string;
  phone?: string;
  email?: string;
  doc_type?: string;
  doc_number?: string;
}

// ── POS Sales — create sale ───────────────────────────────────────────────────

/** Wrapper returned by POST /api/v1/pos/sales/ */
export interface PosSaleCreateResponse {
  sale: {
    id: string;
    number: number;
    status: 'completed' | 'cancelled';
    status_label: string;
    payment_method: string;
    payment_method_label: string;
    total: string;
    subtotal: string;
    discount: string;
    notes: string;
    cash_session_id: string | null;
    created_at: string;
    items_count?: number;
  };
}

// ── POS Session Sales — recent sales list ─────────────────────────────────────

/** Lightweight sale summary returned by GET /api/v1/pos/cash/current/sales/ */
export interface PosCashSessionSale {
  id: string;
  number: number;
  status: 'completed' | 'cancelled';
  status_label: string;
  payment_method: string;
  payment_method_label: string;
  total: string;
  items_count: number;
  created_at: string;
}

/** Wrapper returned by GET /api/v1/pos/cash/current/sales/ */
export interface PosCashCurrentSalesResponse {
  sales: PosCashSessionSale[];
  session_id: string | null;
}
