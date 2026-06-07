/**
 * PR-OFF-04 — Offline sale capture: id helpers, validation, builder, store.
 *
 * Pure unit tests (no React, no IndexedDB) using the in-memory adapter.
 */
import { beforeEach, describe, expect, it } from 'vitest';

import {
  generateClientOrderId,
  isValidClientOrderId,
  shortClientOrderId,
} from '../offline-sale-id';
import {
  buildOfflineSale,
  cartTotal,
  validateOfflineSale,
  type OfflineSaleInput,
} from '../offline-sale-build';
import {
  InMemoryOfflineSalesStorage,
  countOfflineSales,
  enqueueOfflineSale,
  listOfflineSales,
  clearSyncedOfflineSales,
  clearResolvedAndErroredOfflineSales,
  resetRetryableFailedOfflineSales,
} from '../offline-sales-store';
import type { CartItem } from '../../components/SaleItemsPanel';
import type { StoredPosOfflineBootstrap } from '../types';
import type { OfflineSaleQueueItem } from '../offline-sales-types';
import type { PosProduct } from '@/types/pos-cash';

// ── Fixtures ────────────────────────────────────────────────────────────────

function makeSnapshot(
  overrides: Partial<StoredPosOfflineBootstrap> = {},
): StoredPosOfflineBootstrap {
  return {
    bootstrap_version: 1,
    generated_at: '2026-06-06T10:00:00Z',
    saved_at: '2026-06-06T09:30:00Z',
    business: {
      id: 'biz-1',
      name: 'Bar MiRubro',
      currency: 'ARS',
      default_service: 'counter',
      timezone: 'America/Argentina/Buenos_Aires',
    },
    employee: { id: 'emp-1', name: 'Caja', role: 'cashier', code: '0001' },
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
      opened_at: '2026-06-06T09:00:00Z',
      register_name: 'Caja principal',
    },
    categories: [{ id: 'cat-1', name: 'Bebidas', is_active: true }],
    products: [
      {
        id: 'prod-cerveza',
        name: 'Cerveza',
        sku: 'BEER',
        barcode: '111',
        category_id: 'cat-1',
        price: '1000.00',
        stock_min: '0',
        current_stock: '50',
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

function posProduct(overrides: Partial<PosProduct> = {}): PosProduct {
  return {
    id: 'prod-cerveza',
    name: 'Cerveza',
    sku: 'BEER',
    price: '1000.00',
    stock_quantity: '50.00',
    stock_min: '0.00',
    category_id: 'cat-1',
    is_active: true,
    ...overrides,
  };
}

function cart(items: CartItem[] = [{ product: posProduct(), quantity: 2 }]): CartItem[] {
  return items;
}

function makeInput(overrides: Partial<OfflineSaleInput> = {}): OfflineSaleInput {
  return {
    snapshot: makeSnapshot(),
    cart: cart(),
    paymentMethod: 'cash',
    employee: { id: 'emp-1', code: 'EMP-001' },
    ...overrides,
  };
}

// ── Id helpers ──────────────────────────────────────────────────────────────

describe('offline-sale-id', () => {
  it('generates a valid v4 client_order_id', () => {
    const id = generateClientOrderId();
    expect(isValidClientOrderId(id)).toBe(true);
  });

  it('generates unique ids', () => {
    const ids = new Set(Array.from({ length: 50 }, () => generateClientOrderId()));
    expect(ids.size).toBe(50);
  });

  it('rejects malformed ids', () => {
    expect(isValidClientOrderId('not-a-uuid')).toBe(false);
    expect(isValidClientOrderId('')).toBe(false);
  });

  it('shortens an id to 8 chars', () => {
    const id = '12345678-aaaa-4bbb-8ccc-1234567890ab';
    expect(shortClientOrderId(id)).toBe('12345678');
  });
});

// ── Validation ──────────────────────────────────────────────────────────────

describe('validateOfflineSale', () => {
  it('accepts a valid offline sale', () => {
    expect(validateOfflineSale(makeInput())).toEqual({ ok: true });
  });

  it('blocks when there is no snapshot', () => {
    const result = validateOfflineSale(makeInput({ snapshot: null }));
    expect(result.ok).toBe(false);
  });

  it('blocks when the offline policy is disabled', () => {
    const snapshot = makeSnapshot({
      offline_policy: {
        enabled: false,
        mode: 'quick_sale_only',
        expires_in_hours: 24,
        supports_kitchen: false,
        supports_tables: false,
        supports_orders: false,
      },
    });
    expect(validateOfflineSale(makeInput({ snapshot })).ok).toBe(false);
  });

  it('blocks when quick sale is not enabled', () => {
    const snapshot = makeSnapshot({
      operation_settings: {
        pos_quick_sale_enabled: false,
        kitchen_enabled: false,
        tables_enabled: false,
        counter_orders_enabled: false,
      },
    });
    expect(validateOfflineSale(makeInput({ snapshot })).ok).toBe(false);
  });

  it('blocks an empty cart', () => {
    expect(validateOfflineSale(makeInput({ cart: [] })).ok).toBe(false);
  });

  it('blocks when the business requires a customer', () => {
    const snapshot = makeSnapshot({
      commercial_settings: {
        allow_sell_without_stock: true,
        block_sales_if_no_open_cash_session: false,
        require_customer_for_sales: true,
      },
    });
    const result = validateOfflineSale(makeInput({ snapshot }));
    expect(result.ok).toBe(false);
    if (result.ok === false) {
      expect(result.message).toMatch(/requiere cliente/i);
    }
  });

  it('blocks when no open cash session is required but missing', () => {
    const snapshot = makeSnapshot({
      cash_session: null,
      commercial_settings: {
        allow_sell_without_stock: true,
        block_sales_if_no_open_cash_session: true,
        require_customer_for_sales: false,
      },
    });
    const result = validateOfflineSale(makeInput({ snapshot }));
    expect(result.ok).toBe(false);
    if (result.ok === false) {
      expect(result.message).toMatch(/caja abierta/i);
    }
  });

  it('blocks insufficient stock when selling without stock is not allowed', () => {
    const snapshot = makeSnapshot({
      commercial_settings: {
        allow_sell_without_stock: false,
        block_sales_if_no_open_cash_session: false,
        require_customer_for_sales: false,
      },
      products: [
        {
          id: 'prod-cerveza',
          name: 'Cerveza',
          sku: 'BEER',
          barcode: '111',
          category_id: 'cat-1',
          price: '1000.00',
          stock_min: '0',
          current_stock: '1',
          is_active: true,
        },
      ],
    });
    const result = validateOfflineSale(
      makeInput({ snapshot, cart: cart([{ product: posProduct(), quantity: 3 }]) }),
    );
    expect(result.ok).toBe(false);
    if (result.ok === false) {
      expect(result.message).toMatch(/stock suficiente/i);
    }
  });

  it('permits low stock when selling without stock is allowed', () => {
    const snapshot = makeSnapshot({
      commercial_settings: {
        allow_sell_without_stock: true,
        block_sales_if_no_open_cash_session: false,
        require_customer_for_sales: false,
      },
      products: [
        {
          id: 'prod-cerveza',
          name: 'Cerveza',
          sku: 'BEER',
          barcode: '111',
          category_id: 'cat-1',
          price: '1000.00',
          stock_min: '0',
          current_stock: '0',
          is_active: true,
        },
      ],
    });
    const result = validateOfflineSale(
      makeInput({ snapshot, cart: cart([{ product: posProduct(), quantity: 3 }]) }),
    );
    expect(result.ok).toBe(true);
  });
});

// ── Builder ─────────────────────────────────────────────────────────────────

describe('buildOfflineSale', () => {
  it('computes the cart total', () => {
    expect(cartTotal(cart([{ product: posProduct(), quantity: 2 }]))).toBe(2000);
  });

  it('builds a pending queue item with a valid client_order_id', () => {
    const item = buildOfflineSale(makeInput());
    expect(item.status).toBe('pending');
    expect(item.sync_attempts).toBe(0);
    expect(item.last_error).toBeNull();
    expect(item.source).toBe('pos_offline');
    expect(isValidClientOrderId(item.client_order_id)).toBe(true);
    expect(isValidClientOrderId(item.local_id)).toBe(true);
  });

  it('captures items, totals and payment from the cart', () => {
    const item = buildOfflineSale(makeInput());
    expect(item.sale_payload.items).toEqual([
      { product: 'prod-cerveza', quantity: '2', unit_price: '1000.00' },
    ]);
    expect(item.sale_payload.payments).toEqual([{ method: 'cash', amount: '2000.00' }]);
    expect(item.totals_snapshot).toEqual({
      subtotal: '2000.00',
      discount: '0.00',
      total: '2000.00',
      item_count: 2,
    });
    expect(item.payment_snapshot).toEqual([{ method: 'cash', amount: '2000.00' }]);
  });

  it('records snapshot provenance and employee/cash session', () => {
    const item = buildOfflineSale(makeInput());
    expect(item.business_id).toBe('biz-1');
    expect(item.employee_id).toBe('emp-1');
    expect(item.employee_code).toBe('EMP-001');
    expect(item.cash_session_id).toBe('cash-1');
    expect(item.offline_snapshot_generated_at).toBe('2026-06-06T10:00:00Z');
    expect(item.offline_snapshot_saved_at).toBe('2026-06-06T09:30:00Z');
  });

  it('honours injectable now/clientOrderId/localId', () => {
    const item = buildOfflineSale(makeInput(), {
      now: '2026-07-01T00:00:00Z',
      clientOrderId: '12345678-aaaa-4bbb-8ccc-1234567890ab',
      localId: 'local-xyz',
    });
    expect(item.created_at).toBe('2026-07-01T00:00:00Z');
    expect(item.updated_at).toBe('2026-07-01T00:00:00Z');
    expect(item.client_order_id).toBe('12345678-aaaa-4bbb-8ccc-1234567890ab');
    expect(item.local_id).toBe('local-xyz');
  });
});

// ── Store ───────────────────────────────────────────────────────────────────

describe('offline-sales-store', () => {
  let storage: InMemoryOfflineSalesStorage;

  beforeEach(() => {
    storage = new InMemoryOfflineSalesStorage();
  });

  it('enqueues and lists offline sales newest-first', async () => {
    await enqueueOfflineSale(
      buildOfflineSale(makeInput(), { now: '2026-06-06T10:00:00Z', localId: 'a' }),
      storage,
    );
    await enqueueOfflineSale(
      buildOfflineSale(makeInput(), { now: '2026-06-06T11:00:00Z', localId: 'b' }),
      storage,
    );

    const list = await listOfflineSales(storage);
    expect(list.map((s) => s.local_id)).toEqual(['b', 'a']);
  });

  it('counts sales by status', async () => {
    await enqueueOfflineSale(
      buildOfflineSale(makeInput(), { localId: 'a' }),
      storage,
    );
    expect(await countOfflineSales(undefined, storage)).toBe(1);
    expect(await countOfflineSales('pending', storage)).toBe(1);
    expect(await countOfflineSales('synced', storage)).toBe(0);
  });

  it('rejects duplicate local_id', async () => {
    const item = buildOfflineSale(makeInput(), { localId: 'dup' });
    await enqueueOfflineSale(item, storage);
    await expect(enqueueOfflineSale(item, storage)).rejects.toThrow();
  });
});

// ── Clear / retry error recovery (PR-OFF-09) ─────────────────────────────────

describe('offline-sales-store error recovery', () => {
  let storage: InMemoryOfflineSalesStorage;

  function seed(
    localId: string,
    overrides: Partial<OfflineSaleQueueItem>,
  ): OfflineSaleQueueItem {
    const item: OfflineSaleQueueItem = {
      ...buildOfflineSale(makeInput(), { localId }),
      ...overrides,
    };
    return item;
  }

  beforeEach(async () => {
    storage = new InMemoryOfflineSalesStorage();
  });

  it('clearSyncedOfflineSales removes only synced sales', async () => {
    await storage.put(seed('p', { status: 'pending' }));
    await storage.put(seed('fa', { status: 'failed', retryable: true, last_error: 'x' }));
    await storage.put(seed('co', { status: 'conflict', retryable: false }));
    await storage.put(seed('sy', { status: 'synced', server_id: 'srv', synced_at: '2026-06-06T11:00:00Z' }));

    const removed = await clearSyncedOfflineSales(storage);

    expect(removed).toBe(1);
    const remaining = await listOfflineSales(storage);
    expect(remaining.map((s) => s.local_id).sort()).toEqual(['co', 'fa', 'p']);
  });

  it('clearResolvedAndErroredOfflineSales removes synced, failed and conflict but keeps pending and syncing', async () => {
    await storage.put(seed('p', { status: 'pending' }));
    await storage.put(seed('sg', { status: 'syncing' }));
    await storage.put(seed('fa', { status: 'failed', retryable: true, last_error: 'x' }));
    await storage.put(seed('nf', { status: 'failed', retryable: false, last_error: 'Stock' }));
    await storage.put(seed('co', { status: 'conflict', retryable: false, last_error: 'dup' }));
    await storage.put(seed('sy', { status: 'synced', server_id: 'srv' }));

    const removed = await clearResolvedAndErroredOfflineSales(storage);

    expect(removed).toBe(4);
    const remaining = await listOfflineSales(storage);
    expect(remaining.map((s) => s.local_id).sort()).toEqual(['p', 'sg']);
  });

  it('clearResolvedAndErroredOfflineSales removes a synced sale', async () => {
    await storage.put(seed('sy', { status: 'synced', server_id: 'srv' }));
    await clearResolvedAndErroredOfflineSales(storage);
    expect((await listOfflineSales(storage)).some((s) => s.local_id === 'sy')).toBe(false);
  });

  it('clearResolvedAndErroredOfflineSales removes a failed sale (error leaves the panel)', async () => {
    await storage.put(seed('fa', { status: 'failed', retryable: true, last_error: 'x' }));
    await clearResolvedAndErroredOfflineSales(storage);
    expect((await listOfflineSales(storage)).some((s) => s.local_id === 'fa')).toBe(false);
  });

  it('clearResolvedAndErroredOfflineSales removes a conflict sale', async () => {
    await storage.put(seed('co', { status: 'conflict', retryable: false, last_error: 'dup' }));
    await clearResolvedAndErroredOfflineSales(storage);
    expect((await listOfflineSales(storage)).some((s) => s.local_id === 'co')).toBe(false);
  });

  it('clearResolvedAndErroredOfflineSales NEVER removes pending sales', async () => {
    await storage.put(seed('p', { status: 'pending' }));
    const removed = await clearResolvedAndErroredOfflineSales(storage);
    expect(removed).toBe(0);
    expect((await listOfflineSales(storage)).find((s) => s.local_id === 'p')!.status).toBe('pending');
  });

  it('clearResolvedAndErroredOfflineSales NEVER removes syncing sales', async () => {
    await storage.put(seed('sg', { status: 'syncing' }));
    const removed = await clearResolvedAndErroredOfflineSales(storage);
    expect(removed).toBe(0);
    expect((await listOfflineSales(storage)).find((s) => s.local_id === 'sg')!.status).toBe('syncing');
  });

  it('resetRetryableFailedOfflineSales returns retryable failures to pending and clears the error', async () => {
    await storage.put(
      seed('fa', { status: 'failed', retryable: true, last_error: 'Sin conexión', sync_attempts: 2 }),
    );

    const reset = await resetRetryableFailedOfflineSales(storage, '2026-06-06T12:00:00Z');

    expect(reset).toBe(1);
    const list = await listOfflineSales(storage);
    const sale = list.find((s) => s.local_id === 'fa')!;
    expect(sale.status).toBe('pending');
    expect(sale.last_error).toBeNull();
    expect(sale.updated_at).toBe('2026-06-06T12:00:00Z');
  });

  it('preserves client_order_id, sale_payload, created_at and sync_attempts when resetting', async () => {
    const original = seed('fa', {
      status: 'failed',
      retryable: true,
      last_error: 'boom',
      sync_attempts: 3,
      client_order_id: 'order-abc',
    });
    original.sale_payload.client_order_id = 'order-abc';
    await storage.put(original);

    await resetRetryableFailedOfflineSales(storage);

    const sale = (await listOfflineSales(storage)).find((s) => s.local_id === 'fa')!;
    expect(sale.client_order_id).toBe('order-abc');
    expect(sale.sale_payload).toEqual(original.sale_payload);
    expect(sale.created_at).toBe(original.created_at);
    expect(sale.sync_attempts).toBe(3);
  });

  it('never touches pending, conflict, synced or non-retryable failed sales', async () => {
    await storage.put(seed('p', { status: 'pending', last_error: null }));
    await storage.put(seed('co', { status: 'conflict', retryable: false, last_error: 'dup' }));
    await storage.put(seed('sy', { status: 'synced', server_id: 'srv' }));
    await storage.put(seed('nf', { status: 'failed', retryable: false, last_error: 'Stock insuficiente' }));

    const reset = await resetRetryableFailedOfflineSales(storage);

    expect(reset).toBe(0);
    const list = await listOfflineSales(storage);
    expect(list.find((s) => s.local_id === 'p')!.status).toBe('pending');
    expect(list.find((s) => s.local_id === 'co')!.status).toBe('conflict');
    expect(list.find((s) => s.local_id === 'co')!.last_error).toBe('dup');
    expect(list.find((s) => s.local_id === 'sy')!.status).toBe('synced');
    const nonRetryable = list.find((s) => s.local_id === 'nf')!;
    expect(nonRetryable.status).toBe('failed');
    expect(nonRetryable.last_error).toBe('Stock insuficiente');
  });

  it('does not delete any sale', async () => {
    await storage.put(seed('fa', { status: 'failed', retryable: true, last_error: 'x' }));
    await storage.put(seed('nf', { status: 'failed', retryable: false, last_error: 'y' }));

    await resetRetryableFailedOfflineSales(storage);

    expect(await countOfflineSales(undefined, storage)).toBe(2);
  });
});
