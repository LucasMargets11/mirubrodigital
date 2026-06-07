/**
 * PR-OFF-07 — validateOfflineSale snapshot-expiry + pending-limit guardrails.
 *
 * Exercises the new `now` / `unsyncedCount` inputs on the pure validator.
 */
import { describe, expect, it } from 'vitest';

import { validateOfflineSale, type OfflineSaleInput } from '../offline-sale-build';
import {
  MAX_PENDING_OFFLINE_SALES,
  PENDING_LIMIT_MESSAGE,
  SNAPSHOT_EXPIRED_MESSAGE,
} from '../offline-snapshot-policy';
import type { CartItem } from '../../components/SaleItemsPanel';
import type { StoredPosOfflineBootstrap } from '../types';
import type { PosProduct } from '@/types/pos-cash';

function makeSnapshot(
  overrides: Partial<StoredPosOfflineBootstrap> = {},
): StoredPosOfflineBootstrap {
  return {
    bootstrap_version: 1,
    generated_at: '2026-06-06T10:00:00.000Z',
    saved_at: '2026-06-06T10:00:00.000Z',
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
      opened_at: '2026-06-06T09:00:00.000Z',
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
    payment_methods: [{ code: 'cash', label: 'Efectivo' }],
    ...overrides,
  };
}

function posProduct(): PosProduct {
  return {
    id: 'prod-cerveza',
    name: 'Cerveza',
    sku: 'BEER',
    price: '1000.00',
    stock_quantity: '50.00',
    stock_min: '0.00',
    category_id: 'cat-1',
    is_active: true,
  };
}

function makeInput(overrides: Partial<OfflineSaleInput> = {}): OfflineSaleInput {
  const cart: CartItem[] = [{ product: posProduct(), quantity: 1 }];
  return {
    snapshot: makeSnapshot(),
    cart,
    paymentMethod: 'cash',
    employee: { id: 'emp-1', code: 'EMP-001' },
    ...overrides,
  };
}

describe('validateOfflineSale — snapshot expiry (PR-OFF-07)', () => {
  it('allows a sale when the snapshot is still valid', () => {
    const result = validateOfflineSale(makeInput({ now: '2026-06-06T12:00:00.000Z' }));
    expect(result.ok).toBe(true);
  });

  it('blocks a sale when the snapshot has expired', () => {
    const result = validateOfflineSale(makeInput({ now: '2026-06-08T12:00:00.000Z' }));
    expect(result.ok).toBe(false);
    if (result.ok === false) {
      expect(result.message).toBe(SNAPSHOT_EXPIRED_MESSAGE);
    }
  });

  it('does not enforce expiry when `now` is omitted (backwards-compatible)', () => {
    const result = validateOfflineSale(makeInput());
    expect(result.ok).toBe(true);
  });

  it('blocks on expiry even when an open cash session is required', () => {
    // Expiry is checked before the cash rule, so expired data never assumes the
    // snapshot cash session is still valid.
    const result = validateOfflineSale(
      makeInput({
        now: '2026-06-08T12:00:00.000Z',
        snapshot: makeSnapshot({
          cash_session: null,
          commercial_settings: {
            allow_sell_without_stock: true,
            block_sales_if_no_open_cash_session: true,
            require_customer_for_sales: false,
          },
        }),
      }),
    );
    expect(result.ok).toBe(false);
    if (result.ok === false) {
      expect(result.message).toBe(SNAPSHOT_EXPIRED_MESSAGE);
    }
  });
});

describe('validateOfflineSale — pending limit (PR-OFF-07)', () => {
  it('allows a sale below the pending limit', () => {
    const result = validateOfflineSale(
      makeInput({ now: '2026-06-06T12:00:00.000Z', unsyncedCount: MAX_PENDING_OFFLINE_SALES - 1 }),
    );
    expect(result.ok).toBe(true);
  });

  it('blocks a sale once the pending limit is reached', () => {
    const result = validateOfflineSale(
      makeInput({ now: '2026-06-06T12:00:00.000Z', unsyncedCount: MAX_PENDING_OFFLINE_SALES }),
    );
    expect(result.ok).toBe(false);
    if (result.ok === false) {
      expect(result.message).toBe(PENDING_LIMIT_MESSAGE);
    }
  });

  it('does not enforce the limit when `unsyncedCount` is omitted', () => {
    const result = validateOfflineSale(makeInput({ now: '2026-06-06T12:00:00.000Z' }));
    expect(result.ok).toBe(true);
  });
});
