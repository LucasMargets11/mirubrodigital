import { apiGet } from '@/lib/api/client';

import type {
  CashClosureDetail,
  CashClosureListResponse,
  ReportPayment,
  ReportProductsResponse,
  ReportPaymentsResponse,
  ReportSale,
  ReportSaleListResponse,
  ReportSummaryResponse,
  ReportsFilters,
  StockAlertsResponse,
  TopProductsLeaderboardResponse,
} from './types';

function buildQuery(params: Record<string, string | number | undefined | null>) {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return;
    }
    searchParams.append(key, String(value));
  });
  const serialized = searchParams.toString();
  return serialized ? `?${serialized}` : '';
}

function sanitizeFilters(filters: ReportsFilters = {}) {
  const query: Record<string, string | number> = {};
  Object.entries(filters).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return;
    }
    query[key] = value;
  });
  return query;
}

export function getReportsSummary(filters: ReportsFilters = {}) {
  const query = buildQuery(sanitizeFilters(filters));
  return apiGet<ReportSummaryResponse>(`/api/v1/reports/summary/${query}`);
}

export function getReportsSales(filters: ReportsFilters = {}) {
  const query = buildQuery(sanitizeFilters(filters));
  return apiGet<ReportSaleListResponse>(`/api/v1/reports/sales/${query}`);
}

export function getReportsSaleDetail(id: string) {
  return apiGet<ReportSale>(`/api/v1/reports/sales/${id}/`);
}

export function getReportsPayments(filters: ReportsFilters = {}) {
  const query = buildQuery(sanitizeFilters(filters));
  return apiGet<ReportPaymentsResponse>(`/api/v1/reports/payments/${query}`);
}

export function getReportsProducts(filters: ReportsFilters = {}) {
  const query = buildQuery(sanitizeFilters(filters));
  return apiGet<ReportProductsResponse>(`/api/v1/reports/products/${query}`);
}

export function getTopProductsLeaderboard(filters: ReportsFilters = {}, metric: 'amount' | 'units' = 'amount', limit = 10) {
  const query = buildQuery({
    ...sanitizeFilters(filters),
    metric,
    limit,
  });
  return apiGet<TopProductsLeaderboardResponse>(`/api/v1/reports/products/top/${query}`);
}

export function getStockAlerts(limit = 6) {
  const query = buildQuery({ limit });
  return apiGet<StockAlertsResponse>(`/api/v1/reports/stock/alerts/${query}`);
}

export function getCashClosures(filters: ReportsFilters = {}) {
  const query = buildQuery(sanitizeFilters(filters));
  return apiGet<CashClosureListResponse>(`/api/v1/reports/cash/closures/${query}`);
}

export function getCashClosureDetail(id: string) {
  return apiGet<CashClosureDetail>(`/api/v1/reports/cash/closures/${id}/`);
}
