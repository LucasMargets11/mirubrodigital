import { useQuery } from '@tanstack/react-query';

import { ApiError } from '@/lib/api/client';

import { getRestaurantCashSessions, getRestaurantProducts, getRestaurantReportsSummary } from './api';
import type {
  RestaurantCashSessionsParams,
  RestaurantCashSessionsResponse,
  RestaurantProductsParams,
  RestaurantProductsResponse,
  RestaurantReportsSummaryParams,
  RestaurantReportsSummaryResponse,
} from './types';

const summaryKey = ['resto', 'reports', 'summary'];
const productsKey = ['resto', 'reports', 'products'];
const cashSessionsKey = ['resto', 'reports', 'cash-sessions'];

export function useRestaurantReportsSummary(
  params: RestaurantReportsSummaryParams | null,
  options?: { enabled?: boolean },
) {
  const enabled = options?.enabled ?? true;
  return useQuery<RestaurantReportsSummaryResponse>({
    queryKey: [...summaryKey, params],
    queryFn: () => getRestaurantReportsSummary(params as RestaurantReportsSummaryParams),
    enabled: Boolean(params) && enabled,
    retry: (failureCount, error) => shouldRetry(failureCount, error),
    staleTime: 60_000,
  });
}

export function useRestaurantReportsProducts(
  params: RestaurantProductsParams | null,
  options?: { enabled?: boolean },
) {
  const enabled = options?.enabled ?? true;
  return useQuery<RestaurantProductsResponse>({
    queryKey: [...productsKey, params],
    queryFn: () => getRestaurantProducts(params as RestaurantProductsParams),
    enabled: Boolean(params) && enabled,
    retry: (failureCount, error) => shouldRetry(failureCount, error),
    staleTime: 60_000,
  });
}

export function useRestaurantReportsCashSessions(
  params: RestaurantCashSessionsParams | null,
  options?: { enabled?: boolean },
) {
  const enabled = options?.enabled ?? true;
  return useQuery<RestaurantCashSessionsResponse>({
    queryKey: [...cashSessionsKey, params],
    queryFn: () => getRestaurantCashSessions(params as RestaurantCashSessionsParams),
    enabled: Boolean(params) && enabled,
    retry: (failureCount, error) => shouldRetry(failureCount, error),
    staleTime: 30_000,
  });
}

function shouldRetry(failureCount: number, error: unknown) {
  if (error instanceof ApiError && error.status === 403) {
    return false;
  }
  return failureCount < 2;
}
