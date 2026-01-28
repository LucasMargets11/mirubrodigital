import type { CashClosure } from '@/features/reports/types';

export type RestaurantReportsSummaryParams = {
  date_from: string;
  date_to: string;
  compare?: boolean;
  location_id?: string;
};

export type RestaurantPaymentRow = {
  method: string;
  method_label: string;
  amount: string;
  count: number;
};

export type RestaurantSeriesPoint = {
  date: string;
  revenue: string;
  sales_count: number;
};

export type RestaurantReportsSummaryKPIs = {
  revenue_total: string;
  sales_count: number;
  avg_ticket: string;
  cash_sessions_closed: number;
  cash_diff_total: string;
  top_payment_method: RestaurantPaymentRow | null;
};

export type RestaurantReportsSummaryResponse = {
  range: {
    date_from: string;
    date_to: string;
  };
  kpis: RestaurantReportsSummaryKPIs;
  payments: RestaurantPaymentRow[];
  series_daily: RestaurantSeriesPoint[];
  compare?: {
    range: {
      date_from: string;
      date_to: string;
    };
    kpis: RestaurantReportsSummaryKPIs;
    payments: RestaurantPaymentRow[];
    series_daily: RestaurantSeriesPoint[];
  };
};

export type RestaurantProductsParams = {
  date_from: string;
  date_to: string;
  limit?: number;
};

export type RestaurantProductRow = {
  product_id: string | null;
  name: string;
  qty: string;
  revenue: string;
};

export type RestaurantProductsResponse = {
  range: {
    date_from: string;
    date_to: string;
  };
  top: RestaurantProductRow[];
  bottom: RestaurantProductRow[];
};

export type RestaurantCashSessionsParams = {
  date_from: string;
  date_to: string;
  limit?: number;
};

export type RestaurantCashSessionsResponse = {
  range: {
    date_from: string;
    date_to: string;
  };
  results: CashClosure[];
};
