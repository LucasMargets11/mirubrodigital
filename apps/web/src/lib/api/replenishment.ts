import { apiGet, apiPost } from './client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ReplenishmentItem {
  product_id: string;
  quantity: string;
  unit_cost: string;
}

export interface ReplenishmentItemPayload {
  product_id: string;
  quantity: number;
  unit_cost: number;
}

export interface ReplenishmentTransactionSummary {
  id: number;
  amount: string;
  direction: string;
  occurred_at: string;
  status: string;
  account_id: number | null;
  account_name: string | null;
}

export interface ReplenishmentMovementSummary {
  id: string;
  product_name: string | null;
  product_sku: string | null;
  movement_type: string;
  quantity: string;
  unit_cost: string | null;
  line_total: string | null;
  created_at: string;
}

export interface StockReplenishmentList {
  id: string;
  occurred_at: string;
  supplier_name: string;
  invoice_number: string;
  account_id: number | null;
  account_name: string | null;
  total_amount: string;
  status: 'posted' | 'voided';
  transaction_id: number | null;
  created_at: string;
}

export interface StockReplenishmentDetail extends StockReplenishmentList {
  purchase_category_id: number | null;
  purchase_category_name: string | null;
  notes: string;
  transaction: ReplenishmentTransactionSummary | null;
  items: ReplenishmentMovementSummary[];
}

export interface CreateReplenishmentPayload {
  occurred_at: string;
  supplier_name: string;
  invoice_number?: string;
  account_id: number;
  purchase_category_id?: number | null;
  notes?: string;
  items: ReplenishmentItemPayload[];
}

export interface ReplenishmentFilters {
  date_from?: string;
  date_to?: string;
  search?: string;
  account_id?: string;
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

function buildQuery(params: Record<string, string | undefined>): string {
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '') sp.append(k, v);
  });
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export function listReplenishments(filters: ReplenishmentFilters = {}): Promise<StockReplenishmentList[]> {
  const query = buildQuery({
    date_from: filters.date_from,
    date_to: filters.date_to,
    search: filters.search,
    account_id: filters.account_id,
  });
  return apiGet<StockReplenishmentList[]>(`/api/v1/inventory/replenishments/${query}`);
}

export function getReplenishment(id: string): Promise<StockReplenishmentDetail> {
  return apiGet<StockReplenishmentDetail>(`/api/v1/inventory/replenishments/${id}/`);
}

export function createReplenishment(payload: CreateReplenishmentPayload): Promise<StockReplenishmentDetail> {
  return apiPost<StockReplenishmentDetail>('/api/v1/inventory/replenishments/', payload);
}

export function voidReplenishment(id: string, reason: string): Promise<StockReplenishmentDetail> {
  return apiPost<StockReplenishmentDetail>(`/api/v1/inventory/replenishments/${id}/void/`, { reason });
}
