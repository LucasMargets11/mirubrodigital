/**
 * API client for operative POS endpoints (X-Employee-Token auth).
 *
 * All functions accept a `token` argument that is sent as the
 * `X-Employee-Token` header. This is intentionally separate from the
 * owner/staff cookie-based client.ts to avoid auth cross-contamination.
 *
 * Operative endpoints:
 *   POST /api/v1/auth/employee-login/          — public (no token)
 *   GET  /api/v1/pos/me/                       — X-Employee-Token required
 *   GET  /api/v1/pos/capabilities/             — X-Employee-Token required
 *   GET  /api/v1/pos/health/                   — X-Employee-Token required
 *
 * Cash POS endpoints (all require X-Employee-Token):
 *   POST /api/v1/pos/cash/open/
 *   GET  /api/v1/pos/cash/current/
 *   POST /api/v1/pos/cash/current/close/
 *   POST /api/v1/pos/cash/current/movements/
 */
import { ApiError } from '@/lib/api/client';
import type {
  CounterOrderPayload,
  CounterOrderResponse,
} from '@/features/orders/types';
import type {
  EmployeeCapabilities,
  EmployeeLoginRequest,
  EmployeeLoginResponse,
  EmployeeMe,
  PosApiErrorPayload,
  PosHealthResponse,
} from '@/types/employees';
import type {
  PosCashCloseRequest,
  PosCashCurrentMovementsResponse,
  PosCashCurrentSalesResponse,
  PosCashMovement,
  PosCashMovementRequest,
  PosCashOpenRequest,
  PosCashSessionResponse,
  PosCategoriesResponse,
  PosCustomerCreatePayload,
  PosCustomersResponse,
  PosCustomerSummary,
  PosProductsResponse,
  PosSaleCreateResponse,
  PosSalePayload,
} from '@/types/pos-cash';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// ── Internal fetch helper ─────────────────────────────────────────────────────

async function posFetch<T>(
  path: string,
  token: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-Employee-Token': token,
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const payload: PosApiErrorPayload = await response.json().catch(() => ({}));
    const message =
      payload.error ?? payload.detail ?? 'Error inesperado en la API operativa';
    throw new ApiError(message, response.status, payload);
  }

  return response.json() as Promise<T>;
}

// ── Public (no token) ─────────────────────────────────────────────────────────

/**
 * POST /api/v1/auth/employee-login/
 * No authentication header required — this is the auth endpoint itself.
 */
export async function employeeLogin(
  payload: EmployeeLoginRequest,
): Promise<EmployeeLoginResponse> {
  const response = await fetch(`${API_URL}/api/v1/auth/employee-login/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body: PosApiErrorPayload = await response.json().catch(() => ({}));
    const message = body.error ?? body.detail ?? 'Credenciales incorrectas';
    throw new ApiError(message, response.status, body);
  }

  return response.json() as Promise<EmployeeLoginResponse>;
}

// ── Authenticated operative calls (require X-Employee-Token) ─────────────────

/**
 * GET /api/v1/pos/me/
 * Returns operative identity. Accessible even when must_change_pin=true.
 */
export function posGetMe(token: string): Promise<EmployeeMe> {
  return posFetch<EmployeeMe>('/api/v1/pos/me/', token, { method: 'GET' });
}

/**
 * GET /api/v1/pos/capabilities/
 * Returns effective permissions + POS capabilities.
 * Blocked (403 pin_change_required) when must_change_pin=true.
 */
export function posGetCapabilities(token: string): Promise<EmployeeCapabilities> {
  return posFetch<EmployeeCapabilities>('/api/v1/pos/capabilities/', token, {
    method: 'GET',
  });
}

/**
 * GET /api/v1/pos/health/
 * Lightweight token validation probe.
 * Accessible even when must_change_pin=true.
 */
export function posGetHealth(token: string): Promise<PosHealthResponse> {
  return posFetch<PosHealthResponse>('/api/v1/pos/health/', token, {
    method: 'GET',
  });
}

// ── Error helpers ─────────────────────────────────────────────────────────────

/**
 * Returns true if the error is a POS authentication failure
 * (token invalid/expired/missing or employee suspended).
 */
export function isPosAuthError(err: unknown): boolean {
  return err instanceof ApiError && (err.status === 401 || err.status === 403);
}

/**
 * Returns true if the error payload signals a mandatory PIN change is required.
 * This can come from /pos/capabilities/ when must_change_pin=true.
 */
export function isPinChangeRequired(err: unknown): boolean {
  if (!(err instanceof ApiError)) return false;
  const payload = err.payload as PosApiErrorPayload | undefined;
  return err.status === 403 && payload?.code === 'pin_change_required';
}

// ── Cash POS endpoints ────────────────────────────────────────────────────────

/**
 * GET /api/v1/pos/cash/current/
 * Returns { session: PosCashSession | null } for the authenticated employee.
 */
export function posGetCurrentCashSession(token: string): Promise<PosCashSessionResponse> {
  return posFetch<PosCashSessionResponse>('/api/v1/pos/cash/current/', token, {
    method: 'GET',
  });
}

/**
 * POST /api/v1/pos/cash/open/
 * Opens a new cash session. Returns { session: PosCashSession }.
 * Throws ApiError 400 if a session is already open.
 * Throws ApiError 403 if capability 'can_open_cash' is missing.
 */
export function posOpenCashSession(
  token: string,
  payload: PosCashOpenRequest,
): Promise<PosCashSessionResponse> {
  return posFetch<PosCashSessionResponse>('/api/v1/pos/cash/open/', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * POST /api/v1/pos/cash/current/close/
 * Closes the employee's open session. Returns { session: PosCashSession }.
 * Throws ApiError 400 if no session is open.
 * Throws ApiError 403 if capability 'can_close_cash' is missing.
 */
export function posCloseCurrentCashSession(
  token: string,
  payload: PosCashCloseRequest,
): Promise<PosCashSessionResponse> {
  return posFetch<PosCashSessionResponse>('/api/v1/pos/cash/current/close/', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * POST /api/v1/pos/cash/current/movements/
 * Registers an IN/OUT movement in the employee's current session.
 * Returns { movement: PosCashMovement }.
 * Throws ApiError 400 if no session open / invalid amount.
 * Throws ApiError 403 if capability 'can_register_cash_movement' is missing.
 */
export function posCreateCashMovement(
  token: string,
  payload: PosCashMovementRequest,
): Promise<{ movement: PosCashMovement }> {
  return posFetch<{ movement: PosCashMovement }>(
    '/api/v1/pos/cash/current/movements/',
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

/**
 * GET /api/v1/pos/cash/current/movements/
 * Lists movements in the employee's current open session, newest first.
 * Returns { movements: [], session_id: null } when no session is open.
 * Throws ApiError 403 if capability 'can_register_cash_movement' is missing.
 */
export function posGetCurrentCashMovements(
  token: string,
): Promise<PosCashCurrentMovementsResponse> {
  return posFetch<PosCashCurrentMovementsResponse>(
    '/api/v1/pos/cash/current/movements/',
    token,
    { method: 'GET' },
  );
}

/**
 * GET /api/v1/pos/cash/current/sales/
 * Lists recent sales in the employee's current open session, newest first (max 5).
 * Returns { sales: [], session_id: null } when no session is open.
 * Throws ApiError 403 if capability 'can_create_sale' is missing.
 */
export function posGetCurrentCashSales(
  token: string,
): Promise<PosCashCurrentSalesResponse> {
  return posFetch<PosCashCurrentSalesResponse>(
    '/api/v1/pos/cash/current/sales/',
    token,
    { method: 'GET' },
  );
}

// ── Sales POS endpoints ───────────────────────────────────────────────────────

/**
 * POST /api/v1/pos/sales/
 * Creates a sale as the authenticated employee.
 * The server auto-assigns the employee's current open cash session.
 *
 * Throws ApiError 403 if capability 'can_create_sale' is missing.
 * Throws ApiError 400 if items empty / stock insufficient / cash session required.
 */
export function posCreateSale(
  token: string,
  payload: PosSalePayload,
): Promise<PosSaleCreateResponse> {
  return posFetch<PosSaleCreateResponse>('/api/v1/pos/sales/', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * POST /api/v1/pos/orders/counter/
 * Creates a pickup order intended for the kitchen flow from the POS cart.
 */
export function posCreateCounterOrder(
  token: string,
  payload: CounterOrderPayload,
): Promise<CounterOrderResponse> {
  return posFetch<CounterOrderResponse>('/api/v1/pos/orders/counter/', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

// ── Catalog POS endpoints ─────────────────────────────────────────────────────

export interface PosGetProductsParams {
  /** Filter by name or SKU (min 2 chars). */
  search?: string;
  /** Filter to a single category UUID. */
  category_id?: string | null;
  /** When true, only return products with stock_quantity > 0. */
  in_stock_only?: boolean;
  /** Max results (default 100, hard-cap 200). */
  limit?: number;
}

/**
 * GET /api/v1/pos/catalog/products/
 * Returns active products for the employee's business.
 * Supports search, category_id, in_stock_only and limit query params.
 */
export function posGetProducts(
  token: string,
  params: PosGetProductsParams | string = {},
): Promise<PosProductsResponse> {
  // Backwards-compat: callers that pass a bare search string still work.
  const opts: PosGetProductsParams =
    typeof params === 'string' ? { search: params } : params;

  const qs = new URLSearchParams();
  if (opts.search && opts.search.length >= 2) qs.set('search', opts.search);
  if (opts.category_id) qs.set('category_id', opts.category_id);
  if (opts.in_stock_only) qs.set('in_stock_only', 'true');
  if (opts.limit) qs.set('limit', String(opts.limit));

  const query = qs.toString() ? `?${qs.toString()}` : '';
  return posFetch<PosProductsResponse>(`/api/v1/pos/catalog/products/${query}`, token, {
    method: 'GET',
  });
}

/**
 * GET /api/v1/pos/catalog/categories/
 * Returns active categories for the employee's business, with products_count.
 */
export function posGetCategories(
  token: string,
): Promise<PosCategoriesResponse> {
  return posFetch<PosCategoriesResponse>('/api/v1/pos/catalog/categories/', token, {
    method: 'GET',
  });
}

// ── Customer POS endpoints ────────────────────────────────────────────────────

/**
 * GET /api/v1/pos/customers/?search=<str>
 * Searches active customers for the employee's business.
 * Returns empty results when search < 2 chars (enforced by backend).
 */
export function posSearchCustomers(
  token: string,
  search: string,
): Promise<PosCustomersResponse> {
  const params = new URLSearchParams();
  if (search && search.length >= 2) {
    params.set('search', search);
  }
  const qs = params.toString() ? `?${params.toString()}` : '';
  return posFetch<PosCustomersResponse>(`/api/v1/pos/customers/${qs}`, token, {
    method: 'GET',
  });
}

/**
 * POST /api/v1/pos/customers/
 * Creates a minimal customer record from the POS terminal.
 * Returns the created customer summary.
 * Throws ApiError 400 on validation errors (e.g. empty name).
 */
export function posCreateCustomer(
  token: string,
  payload: PosCustomerCreatePayload,
): Promise<PosCustomerSummary> {
  return posFetch<PosCustomerSummary>('/api/v1/pos/customers/', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
