import { useQuery } from '@tanstack/react-query';

import {
  getCashClosureDetail,
  getCashClosures,
  getReportsPayments,
  getReportsProducts,
  getReportsSaleDetail,
  getReportsSales,
  getReportsSummary,
  getStockAlerts,
  getTopProductsLeaderboard,
} from './api';
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

const summaryKey = ['reports', 'summary'];
const salesKey = ['reports', 'sales'];
const paymentsKey = ['reports', 'payments'];
const closuresKey = ['reports', 'cash', 'closures'];
const productsKey = ['reports', 'products'];
const topProductsKey = ['reports', 'products-top'];
const stockAlertsKey = ['reports', 'stock-alerts'];

export function useReportsSummary(filters: ReportsFilters) {
  return useQuery<ReportSummaryResponse>({
    queryKey: [...summaryKey, filters],
    queryFn: () => getReportsSummary(filters),
  });
}

export function useReportsSales(filters: ReportsFilters) {
  return useQuery<ReportSaleListResponse>({
    queryKey: [...salesKey, filters],
    queryFn: () => getReportsSales(filters),
  });
}

export function useReportSaleDetail(id?: string) {
  return useQuery<ReportSale>({
    queryKey: [...salesKey, 'detail', id],
    queryFn: () => getReportsSaleDetail(id as string),
    enabled: Boolean(id),
  });
}

export function useReportsPayments(filters: ReportsFilters) {
  return useQuery<ReportPaymentsResponse>({
    queryKey: [...paymentsKey, filters],
    queryFn: () => getReportsPayments(filters),
  });
}

export function useReportsProducts(filters: ReportsFilters) {
  return useQuery<ReportProductsResponse>({
    queryKey: [...productsKey, filters],
    queryFn: () => getReportsProducts(filters),
  });
}

export function useTopProductsLeaderboard(filters: ReportsFilters, metric: 'amount' | 'units', limit = 10) {
  return useQuery<TopProductsLeaderboardResponse>({
    queryKey: [...topProductsKey, filters, metric, limit],
    queryFn: () => getTopProductsLeaderboard(filters, metric, limit),
  });
}

export function useStockAlerts(limit = 6) {
  return useQuery<StockAlertsResponse>({
    queryKey: [...stockAlertsKey, limit],
    queryFn: () => getStockAlerts(limit),
  });
}

export function useCashClosures(filters: ReportsFilters) {
  return useQuery<CashClosureListResponse>({
    queryKey: [...closuresKey, filters],
    queryFn: () => getCashClosures(filters),
  });
}

export function useCashClosureDetail(id?: string) {
  return useQuery<CashClosureDetail>({
    queryKey: [...closuresKey, 'detail', id],
    queryFn: () => getCashClosureDetail(id as string),
    enabled: Boolean(id),
  });
}
