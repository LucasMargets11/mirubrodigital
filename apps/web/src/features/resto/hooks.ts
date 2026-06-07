import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiError } from '@/lib/api/client';

import {
  fetchRestaurantOperationSettings,
  updateRestaurantOperationSettings,
} from './api';
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

export type OrderChannelKey = 'dine_in' | 'pickup' | 'delivery';

/**
 * Derive the order channels a business can currently create, based on its
 * operative configuration. Channels are granular and independent:
 *  - dine_in: requires both tables and salón orders to be enabled.
 *  - pickup:  available whenever pickup/mostrador orders are enabled.
 *  - delivery: available whenever delivery orders are enabled.
 */
export function getAvailableOrderChannels(
  settings: RestaurantOperationSettings,
): OrderChannelKey[] {
  const channels: OrderChannelKey[] = [];
  if (settings.tables_enabled && settings.allow_dine_in_orders) {
    channels.push('dine_in');
  }
  if (settings.allow_pickup_orders) {
    channels.push('pickup');
  }
  if (settings.allow_delivery_orders) {
    channels.push('delivery');
  }
  return channels;
}

export function useUpdateRestaurantOperationSettings() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: Partial<RestaurantOperationSettings>) =>
      updateRestaurantOperationSettings(payload),
    onSuccess: (data) => {
      queryClient.setQueryData(restoOperationKeys.settings(), data);
      queryClient.invalidateQueries({ queryKey: restoOperationKeys.settings() });
      queryClient.invalidateQueries({ queryKey: ['resto'] });
      queryClient.invalidateQueries({ queryKey: ['tables'] });
      queryClient.invalidateQueries({ queryKey: ['kitchen-board'] });
      queryClient.invalidateQueries({ queryKey: ['pos'] });
    },
  });
}