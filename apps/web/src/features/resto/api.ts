import { apiGet, apiPatch } from '@/lib/api/client';

import type { RestaurantOperationSettings } from './types';

export function fetchRestaurantOperationSettings() {
  return apiGet<RestaurantOperationSettings>('/api/v1/resto/settings/operation/');
}

export function updateRestaurantOperationSettings(payload: Partial<RestaurantOperationSettings>) {
  return apiPatch<RestaurantOperationSettings>('/api/v1/resto/settings/operation/', payload);
}