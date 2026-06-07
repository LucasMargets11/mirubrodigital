/**
 * PR-OFF-10 — POS-safe operation settings.
 *
 * The POS must NOT call the owner/admin endpoint
 * `/api/v1/resto/settings/operation/` (it 401s for employee sessions). These
 * tests cover the pure snapshot mapper, the hook reading the POS bootstrap
 * snapshot, and a regression guard that the owner/admin settings API is never
 * invoked.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  posOperationSettingsFromSnapshot,
  usePosOperationSettings,
} from '../pos-operation-settings';
import { DEFAULT_RESTAURANT_OPERATION_SETTINGS } from '@/features/resto/types';
import type { OfflineOperationSettings } from '../types';

const mocks = vi.hoisted(() => ({
  snapshot: null as { operation_settings: OfflineOperationSettings } | null,
  fetchRestaurantOperationSettings: vi.fn(),
  updateRestaurantOperationSettings: vi.fn(),
}));

vi.mock('../bootstrap-hooks', () => ({
  usePosOfflineSnapshot: () => ({ data: mocks.snapshot, isLoading: false }),
}));

// Spy on the owner/admin settings API so we can assert the POS never calls it.
vi.mock('@/features/resto/api', () => ({
  fetchRestaurantOperationSettings: (...args: unknown[]) =>
    mocks.fetchRestaurantOperationSettings(...args),
  updateRestaurantOperationSettings: (...args: unknown[]) =>
    mocks.updateRestaurantOperationSettings(...args),
}));

function makeOps(
  overrides: Partial<OfflineOperationSettings> = {},
): OfflineOperationSettings {
  return {
    pos_quick_sale_enabled: true,
    kitchen_enabled: false,
    tables_enabled: false,
    counter_orders_enabled: false,
    ...overrides,
  };
}

function Probe() {
  const settings = usePosOperationSettings();
  return <span data-testid="settings">{JSON.stringify(settings)}</span>;
}

function readSettings(): ReturnType<typeof usePosOperationSettings> {
  return JSON.parse(screen.getByTestId('settings').textContent ?? '{}');
}

beforeEach(() => {
  mocks.snapshot = null;
  mocks.fetchRestaurantOperationSettings.mockReset();
  mocks.updateRestaurantOperationSettings.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('posOperationSettingsFromSnapshot', () => {
  it('returns safe defaults when there is no snapshot', () => {
    expect(posOperationSettingsFromSnapshot(null)).toEqual(
      DEFAULT_RESTAURANT_OPERATION_SETTINGS,
    );
    expect(posOperationSettingsFromSnapshot(undefined)).toEqual(
      DEFAULT_RESTAURANT_OPERATION_SETTINGS,
    );
  });

  it('maps the snapshot flags and forces quick_sale as the default mode', () => {
    const result = posOperationSettingsFromSnapshot(
      makeOps({
        pos_quick_sale_enabled: true,
        kitchen_enabled: true,
        tables_enabled: true,
        counter_orders_enabled: true,
      }),
    );

    expect(result.pos_quick_sale_enabled).toBe(true);
    expect(result.kitchen_enabled).toBe(true);
    expect(result.tables_enabled).toBe(true);
    expect(result.counter_orders_enabled).toBe(true);
    // default_pos_mode is not part of the POS bootstrap → always quick_sale.
    expect(result.default_pos_mode).toBe('quick_sale');
  });

  it('reflects disabled flags from the snapshot', () => {
    const result = posOperationSettingsFromSnapshot(
      makeOps({ pos_quick_sale_enabled: false, kitchen_enabled: false }),
    );
    expect(result.pos_quick_sale_enabled).toBe(false);
    expect(result.kitchen_enabled).toBe(false);
  });
});

describe('usePosOperationSettings', () => {
  it('returns defaults when no snapshot is available', () => {
    render(<Probe />);
    expect(readSettings()).toEqual(DEFAULT_RESTAURANT_OPERATION_SETTINGS);
  });

  it('derives settings from the POS bootstrap snapshot', () => {
    mocks.snapshot = {
      operation_settings: makeOps({ kitchen_enabled: true, counter_orders_enabled: true }),
    };
    render(<Probe />);
    const settings = readSettings();
    expect(settings.kitchen_enabled).toBe(true);
    expect(settings.counter_orders_enabled).toBe(true);
    expect(settings.default_pos_mode).toBe('quick_sale');
  });

  it('never calls the owner/admin operation-settings endpoint', () => {
    mocks.snapshot = { operation_settings: makeOps() };
    render(<Probe />);
    expect(mocks.fetchRestaurantOperationSettings).not.toHaveBeenCalled();
    expect(mocks.updateRestaurantOperationSettings).not.toHaveBeenCalled();
  });
});
