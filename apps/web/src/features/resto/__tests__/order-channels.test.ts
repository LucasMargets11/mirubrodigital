import { describe, expect, it } from 'vitest';

import { getAvailableOrderChannels } from '../hooks';
import {
  DEFAULT_RESTAURANT_OPERATION_SETTINGS,
  type RestaurantOperationSettings,
} from '../types';

function makeSettings(
  overrides: Partial<RestaurantOperationSettings> = {},
): RestaurantOperationSettings {
  return { ...DEFAULT_RESTAURANT_OPERATION_SETTINGS, ...overrides };
}

describe('getAvailableOrderChannels', () => {
  it('includes dine_in only when tables and salón orders are both enabled', () => {
    expect(
      getAvailableOrderChannels(
        makeSettings({ tables_enabled: true, allow_dine_in_orders: true }),
      ),
    ).toContain('dine_in');
  });

  it('excludes dine_in when tables are disabled even if salón orders are allowed', () => {
    const channels = getAvailableOrderChannels(
      makeSettings({ tables_enabled: false, allow_dine_in_orders: true }),
    );
    expect(channels).not.toContain('dine_in');
  });

  it('excludes dine_in when salón orders are disabled even if tables are enabled', () => {
    const channels = getAvailableOrderChannels(
      makeSettings({ tables_enabled: true, allow_dine_in_orders: false }),
    );
    expect(channels).not.toContain('dine_in');
  });

  it('includes pickup whenever pickup orders are enabled, regardless of tables', () => {
    const channels = getAvailableOrderChannels(
      makeSettings({
        tables_enabled: false,
        allow_dine_in_orders: false,
        allow_pickup_orders: true,
      }),
    );
    expect(channels).toEqual(['pickup']);
  });

  it('includes delivery whenever delivery orders are enabled, regardless of tables', () => {
    const channels = getAvailableOrderChannels(
      makeSettings({
        tables_enabled: false,
        allow_dine_in_orders: false,
        allow_pickup_orders: false,
        allow_delivery_orders: true,
      }),
    );
    expect(channels).toEqual(['delivery']);
  });

  it('returns all three channels when everything is enabled', () => {
    const channels = getAvailableOrderChannels(
      makeSettings({
        tables_enabled: true,
        allow_dine_in_orders: true,
        allow_pickup_orders: true,
        allow_delivery_orders: true,
      }),
    );
    expect(channels).toEqual(['dine_in', 'pickup', 'delivery']);
  });

  it('returns an empty list when all channels are disabled', () => {
    const channels = getAvailableOrderChannels(
      makeSettings({
        tables_enabled: false,
        allow_dine_in_orders: false,
        allow_pickup_orders: false,
        allow_delivery_orders: false,
      }),
    );
    expect(channels).toEqual([]);
  });
});
