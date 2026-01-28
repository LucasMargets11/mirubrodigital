import { apiGet } from '@/lib/api/client';

import type {
  RestaurantCashSessionsParams,
  RestaurantCashSessionsResponse,
  RestaurantProductsParams,
  RestaurantProductsResponse,
  RestaurantReportsSummaryParams,
  RestaurantReportsSummaryResponse,
} from './types';

function buildQuery(params: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return;
    }
    if (typeof value === 'boolean') {
      search.set(key, value ? '1' : '0');
      return;
    }
    search.set(key, String(value));
  });
  const query = search.toString();
  return query ? `?${query}` : '';
}

export function getRestaurantReportsSummary(params: RestaurantReportsSummaryParams) {
  const query = buildQuery({
    date_from: params.date_from,
    date_to: params.date_to,
    compare: params.compare,
    location_id: params.location_id,
  });
  return apiGet<RestaurantReportsSummaryResponse>(`/api/v1/restaurant/reports/summary/${query}`);
}

export function getRestaurantProducts(params: RestaurantProductsParams) {
  const query = buildQuery({
    date_from: params.date_from,
    date_to: params.date_to,
    limit: params.limit,
  });
  return apiGet<RestaurantProductsResponse>(`/api/v1/restaurant/reports/products/${query}`);
}

export function getRestaurantCashSessions(params: RestaurantCashSessionsParams) {
  const query = buildQuery({
    date_from: params.date_from,
    date_to: params.date_to,
    limit: params.limit,
  });
  return apiGet<RestaurantCashSessionsResponse>(`/api/v1/restaurant/reports/cash-sessions/${query}`);
}
