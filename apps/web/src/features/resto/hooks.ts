import { useQuery } from '@tanstack/react-query';

import { ApiError } from '@/lib/api/client';

import { fetchRestaurantOperationSettings } from './api';
import {
  DEFAULT_RESTAURANT_OPERATION_SETTINGS,
  type RestaurantOperationSettings,
} from './types';

export const restoOperationKeys = {
  settings: () => ['resto', 'operation-settings'] as const,
};

export function useRestaurantOperationSettings(options?: { enabled?: boolean }) {
  return useQuery<RestaurantOperationSettings, ApiError>({
    queryKey: restoOperationKeys.settings(),
    queryFn: () => fetchRestaurantOperationSettings(),
    enabled: options?.enabled ?? true,
    retry: (failureCount, error) => {
      if (error.status === 403) return false;
      return failureCount < 2;
    },
    staleTime: 60_000,
  });
}

export function getEffectiveRestaurantOperationSettings(
  settings: RestaurantOperationSettings | undefined,
): RestaurantOperationSettings {
  return settings ?? DEFAULT_RESTAURANT_OPERATION_SETTINGS;
}