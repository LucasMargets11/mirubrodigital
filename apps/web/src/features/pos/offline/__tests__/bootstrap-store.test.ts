/**
 * PR-OFF-02B — Offline bootstrap store + IndexedDB persistence layer.
 *
 * Uses the in-memory storage adapter so the store logic can be exercised
 * without IndexedDB in the test environment.
 */
import { beforeEach, describe, expect, it } from 'vitest';

import { InMemoryBootstrapStorage } from '../db';
import {
  buildStoredSnapshot,
  clearBootstrapSnapshot,
  loadBootstrapSnapshot,
  saveBootstrapSnapshot,
} from '../bootstrap-store';
import type { BootstrapStorage } from '../db';
import type { PosOfflineBootstrapPayload, StoredPosOfflineBootstrap } from '../types';

function makePayload(
  overrides: Partial<PosOfflineBootstrapPayload> = {},
): PosOfflineBootstrapPayload {
  return {
    bootstrap_version: 1,
    generated_at: '2026-06-01T10:00:00Z',
    business: {
      id: 'biz-1',
      name: 'Bar MiRubro',
      currency: 'ARS',
      default_service: 'counter',
      timezone: 'America/Argentina/Buenos_Aires',
    },
    employee: { id: 'emp-1', name: 'Caja 1', role: 'cashier', code: '0001' },
    offline_policy: {
      enabled: true,
      mode: 'quick_sale_only',
      expires_in_hours: 24,
      supports_kitchen: false,
      supports_tables: false,
      supports_orders: false,
    },
    commercial_settings: {
      allow_sell_without_stock: true,
      block_sales_if_no_open_cash_session: true,
      require_customer_for_sales: false,
    },
    operation_settings: {
      pos_quick_sale_enabled: true,
      kitchen_enabled: false,
      tables_enabled: false,
      counter_orders_enabled: false,
    },
    cash_session: {
      id: 'cash-1',
      status: 'open',
      opened_at: '2026-06-01T09:00:00Z',
      register_name: 'Caja principal',
    },
    categories: [
      { id: 'cat-1', name: 'Bebidas', is_active: true },
      { id: 'cat-2', name: 'Comidas', is_active: true },
    ],
    products: [
      {
        id: 'prod-1',
        name: 'Cerveza',
        sku: 'BEER',
        barcode: '111',
        category_id: 'cat-1',
        price: '1000.00',
        stock_min: '0',
        current_stock: '50',
        is_active: true,
      },
      {
        id: 'prod-2',
        name: 'Pizza',
        sku: 'PIZZA',
        barcode: '222',
        category_id: 'cat-2',
        price: '5000.00',
        stock_min: '0',
        current_stock: '10',
        is_active: true,
      },
    ],
    payment_methods: [
      { code: 'cash', label: 'Efectivo' },
      { code: 'card', label: 'Tarjeta' },
    ],
    ...overrides,
  };
}

describe('buildStoredSnapshot', () => {
  it('stamps saved_at on top of the payload', () => {
    const stored = buildStoredSnapshot(makePayload(), '2026-06-01T12:00:00Z');
    expect(stored.saved_at).toBe('2026-06-01T12:00:00Z');
    expect(stored.products).toHaveLength(2);
  });
});

describe('bootstrap-store with InMemoryBootstrapStorage', () => {
  let storage: BootstrapStorage;

  beforeEach(() => {
    storage = new InMemoryBootstrapStorage();
  });

  it('returns null when nothing is persisted', async () => {
    await expect(loadBootstrapSnapshot(storage)).resolves.toBeNull();
  });

  it('persists products, categories and payment methods', async () => {
    await saveBootstrapSnapshot(makePayload(), storage);

    const loaded = await loadBootstrapSnapshot(storage);
    expect(loaded).not.toBeNull();
    expect(loaded?.products.map((p) => p.id)).toEqual(['prod-1', 'prod-2']);
    expect(loaded?.categories.map((c) => c.id)).toEqual(['cat-1', 'cat-2']);
    expect(loaded?.payment_methods.map((m) => m.code)).toEqual(['cash', 'card']);
    expect(loaded?.business.name).toBe('Bar MiRubro');
    expect(loaded?.offline_policy.enabled).toBe(true);
    expect(loaded?.saved_at).toBeTruthy();
  });

  it('replaces the previous snapshot on a new download', async () => {
    await saveBootstrapSnapshot(makePayload(), storage);
    await saveBootstrapSnapshot(
      makePayload({
        products: [
          {
            id: 'prod-9',
            name: 'Agua',
            sku: 'WATER',
            barcode: '999',
            category_id: 'cat-1',
            price: '500.00',
            stock_min: '0',
            current_stock: '99',
            is_active: true,
          },
        ],
        payment_methods: [{ code: 'transfer', label: 'Transferencia' }],
      }),
      storage,
    );

    const loaded = await loadBootstrapSnapshot(storage);
    expect(loaded?.products.map((p) => p.id)).toEqual(['prod-9']);
    expect(loaded?.payment_methods.map((m) => m.code)).toEqual(['transfer']);
  });

  it('keeps the prior snapshot when a save fails', async () => {
    await saveBootstrapSnapshot(makePayload(), storage);

    // Wrap the storage so the next save rejects, simulating a failed refresh.
    const failing: BootstrapStorage = {
      load: () => storage.load(),
      clear: () => storage.clear(),
      save: () => Promise.reject(new Error('boom')),
    };

    await expect(
      saveBootstrapSnapshot(makePayload({ products: [] }), failing),
    ).rejects.toThrow('boom');

    const loaded = await loadBootstrapSnapshot(storage);
    expect(loaded?.products).toHaveLength(2);
  });

  it('clears the persisted snapshot', async () => {
    await saveBootstrapSnapshot(makePayload(), storage);
    await clearBootstrapSnapshot(storage);
    await expect(loadBootstrapSnapshot(storage)).resolves.toBeNull();
  });

  it('never persists tokens or other sensitive fields', async () => {
    await saveBootstrapSnapshot(makePayload(), storage);
    const loaded = (await loadBootstrapSnapshot(storage)) as StoredPosOfflineBootstrap;
    const serialized = JSON.stringify(loaded).toLowerCase();
    expect(serialized).not.toContain('token');
    expect(serialized).not.toContain('pin');
    expect(serialized).not.toContain('password');
  });
});
