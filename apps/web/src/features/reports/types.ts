import type { PaymentMethod, Sale, SaleStatus } from '@/features/gestion/types';

export type ReportRange = {
  from: string;
  to: string;
  group_by: 'day' | 'week' | 'month';
};

export type ReportKpis = {
  gross_sales_total: string;
  net_sales_total: string;
  discounts_total: string;
  sales_count: number;
  avg_ticket: string;
  units_sold: string;
  cancellations_count: number;
};

export type ReportSeriesPoint = {
  period: string;
  gross_sales: string;
  sales_count: number;
  avg_ticket: string;
};

export type PaymentBreakdownRow = {
  method: string;
  method_label: string;
  amount_total: string;
  payments_count: number;
  sales_count: number;
};

export type TopProductRow = {
  name: string;
  quantity: string;
  amount_total: string;
};

export type TopProductLeaderboardItem = {
  product_id: string | null;
  name: string;
  units: string;
  amount_total: string;
  share_pct: string;
};

export type TopProductsLeaderboardResponse = {
  range: {
    from: string;
    to: string;
  };
  metric: 'amount' | 'units';
  items: TopProductLeaderboardItem[];
};

export type StockAlertStatus = 'OUT' | 'LOW';

export type StockAlertRow = {
  product_id: string;
  name: string;
  stock: string;
  threshold: string;
  status: StockAlertStatus;
};

export type StockAlertsResponse = {
  low_stock_threshold_default: string;
  out_of_stock_count: number;
  low_stock_count: number;
  items: StockAlertRow[];
};

export type ReportSummaryResponse = {
  range: ReportRange;
  kpis: ReportKpis;
  series: ReportSeriesPoint[];
  payments_breakdown: PaymentBreakdownRow[];
  top_products: TopProductRow[];
};

export type ReportsFilters = {
  from?: string;
  to?: string;
  group_by?: 'day' | 'week' | 'month';
  status?: string;
  payment_method?: string;
  user_id?: string;
  register_id?: string;
  method?: string;
  limit?: string | number;
  offset?: string | number;
  q?: string;
};

export type ReportSale = Sale & {
  cashier?: {
    id: string;
    name: string;
    email: string;
  } | null;
  payments_summary?: Array<{
    method: string;
    method_label: string;
    amount: string;
  }>;
};

export type PaginatedResponse<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export type ReportSaleListResponse = PaginatedResponse<ReportSale>;

export type ReportProduct = {
  product_id: string | null;
  name: string;
  sku: string;
  quantity: string;
  amount_total: string;
  sales_count: number;
  share: string;
};

export type ReportProductsResponse = PaginatedResponse<ReportProduct> & {
  totals: {
    products_count: number;
    units: string;
    gross_sales: string;
    avg_price: string;
  };
};

export type ReportPayment = {
  id: string;
  sale_id: string;
  sale_number: number;
  sale_total: string;
  session_id: string;
  register: {
    id: string;
    name: string;
  } | null;
  method: string;
  method_label: string;
  amount: string;
  reference: string;
  created_at: string;
  cashier: {
    id: string;
    name: string;
    email: string;
  } | null;
};

export type ReportPaymentsResponse = {
  breakdown: PaymentBreakdownRow[];
  results: ReportPayment[];
  count: number;
  next: string | null;
  previous: string | null;
};

export type CashClosureUser = {
  id: string;
  name: string;
  email: string;
};

export type CashClosure = {
  id: string;
  status: 'open' | 'closed';
  register: { id: string; name: string } | null;
  opened_at: string;
  closed_at: string | null;
  opening_cash_amount: string;
  expected_cash: string | null;
  counted_cash: string | null;
  difference: string | null;
  note: string;
  opened_by: CashClosureUser | null;
  closed_by: CashClosureUser | null;
  opened_by_name?: string | null;
};

export type CashClosureListResponse = PaginatedResponse<CashClosure>;

export type CashMovementSummary = {
  id: string;
  movement_type: 'in' | 'out';
  category: string;
  method: string;
  amount: string;
  note: string;
  created_by: CashClosureUser | null;
  created_at: string;
};

export type CashPaymentSummary = {
  id: string;
  sale_id: string;
  sale_number: number;
  amount: string;
  reference: string;
  created_at: string;
  customer_name?: string | null;
};

export type CashClosureSaleSummary = {
  id: string;
  number: number;
  status: SaleStatus;
  status_label: string;
  payment_method: PaymentMethod;
  payment_method_label: string;
  customer_id: string | null;
  customer_name: string | null;
  subtotal: string;
  discount: string;
  total: string;
  created_at: string;
  items_count: number;
  paid_total: string;
  balance: string;
};

export type CashClosureProductSummary = {
  product_id: string | null;
  name: string;
  quantity: string;
  amount_total: string;
  sales_count: number;
};

export type CashClosureDetail = CashClosure & {
  expected_breakdown: {
    saldo_inicial: string;
    cash_sales_total: string;
    movements_in_total: string;
    movements_out_total: string;
    expected_cash: string;
  };
  payments_summary: {
    payments_total: string;
    payments_by_method: Record<string, string>;
  };
  cash_sales: CashPaymentSummary[];
  sales: CashClosureSaleSummary[];
  products_summary: CashClosureProductSummary[];
  movements: CashMovementSummary[];
};
