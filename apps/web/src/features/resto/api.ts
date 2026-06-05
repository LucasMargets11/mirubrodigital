import { apiGet } from '@/lib/api/client';

import type { RestaurantOperationSettings } from './types';

export function fetchRestaurantOperationSettings() {
  return apiGet<RestaurantOperationSettings>('/api/v1/resto/settings/operation/');
}