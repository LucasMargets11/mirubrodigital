/**
 * PR-OFF-07 — Offline snapshot safety policy (pure helpers).
 *
 * Covers snapshot expiry evaluation, the "expiring soon" warning window and the
 * unsynced pending-queue limit. No React, no IndexedDB.
 */
import { describe, expect, it } from 'vitest';

import {
  MAX_PENDING_OFFLINE_SALES,
  SNAPSHOT_EXPIRY_WARNING_HOURS,
  countUnsyncedOfflineSales,
  evaluateSnapshotExpiry,
  isAtPendingLimit,
} from '../offline-snapshot-policy';
import type { OfflineSaleQueueItem, OfflineSaleStatus } from '../offline-sales-types';
import type { StoredPosOfflineBootstrap } from '../types';

// ── Fixtures ────────────────────────────────────────────────────────────────

const NOW = new Date('2026-06-06T12:00:00.000Z');

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
    categories: [],
    products: [],
    payment_methods: [],
    ...overrides,
  };
}

function makeSale(status: OfflineSaleStatus): OfflineSaleQueueItem {
  const clientOrderId = `00000000-0000-4000-8000-${Math.random()
    .toString(16)
    .slice(2, 14)
    .padEnd(12, '0')}`;
  return {
    local_id: clientOrderId,
    client_order_id: clientOrderId,
    business_id: 'biz-1',
    employee_id: 'emp-1',
    employee_code: '0001',
    cash_session_id: 'cash-1',
    created_at: '2026-06-06T10:00:00.000Z',
    updated_at: '2026-06-06T10:00:00.000Z',
    status,
    sync_attempts: 0,
    last_error: null,
    retryable: true,
    server_id: null,
    synced_at: null,
    duplicate_ack: false,
    sale_payload: {
      client_order_id: clientOrderId,
      items: [{ product: 'prod-1', quantity: '1', unit_price: '1000.00' }],
      payments: [{ method: 'cash', amount: '1000.00' }],
      note: '',
      source: 'pos_offline',
    },
    totals_snapshot: { subtotal: '1000.00', discount: '0.00', total: '1000.00', item_count: 1 },
    payment_snapshot: [{ method: 'cash', amount: '1000.00' }],
    source: 'pos_offline',
    offline_snapshot_generated_at: '2026-06-06T09:00:00.000Z',
    offline_snapshot_saved_at: '2026-06-06T09:30:00.000Z',
  };
}

// ── evaluateSnapshotExpiry ───────────────────────────────────────────────────

describe('evaluateSnapshotExpiry', () => {
  it('reports a fresh snapshot as not expired with hours remaining', () => {
    // generated 2h ago, expires in 24h → ~22h left.
    const expiry = evaluateSnapshotExpiry(makeSnapshot(), NOW);
    expect(expiry.isExpired).toBe(false);
    expect(expiry.isExpiringSoon).toBe(false);
    expect(expiry.hoursUntilExpiry).toBe(22);
    expect(expiry.expiresAt).toBe('2026-06-07T10:00:00.000Z');
  });

  it('reports a past snapshot as expired with zero hours left', () => {
    const snapshot = makeSnapshot({ generated_at: '2026-06-05T10:00:00.000Z' });
    const expiry = evaluateSnapshotExpiry(snapshot, NOW);
    expect(expiry.isExpired).toBe(true);
    expect(expiry.isExpiringSoon).toBe(false);
    expect(expiry.hoursUntilExpiry).toBe(0);
  });

  it('flags a snapshot inside the warning window as expiring soon', () => {
    // generated 23h ago, expires in 24h → 1h left (<= warning threshold).
    const snapshot = makeSnapshot({ generated_at: '2026-06-05T13:00:00.000Z' });
    const expiry = evaluateSnapshotExpiry(snapshot, NOW);
    expect(expiry.isExpired).toBe(false);
    expect(expiry.isExpiringSoon).toBe(true);
    expect(expiry.hoursUntilExpiry).toBeLessThanOrEqual(SNAPSHOT_EXPIRY_WARNING_HOURS);
  });

  it('treats a null snapshot as expired (fail-safe)', () => {
    const expiry = evaluateSnapshotExpiry(null, NOW);
    expect(expiry.isExpired).toBe(true);
    expect(expiry.expiresAt).toBeNull();
    expect(expiry.hoursUntilExpiry).toBeNull();
  });

  it('treats an invalid generated_at as expired (fail-safe)', () => {
    const snapshot = makeSnapshot({ generated_at: 'not-a-date' });
    const expiry = evaluateSnapshotExpiry(snapshot, NOW);
    expect(expiry.isExpired).toBe(true);
    expect(expiry.expiresAt).toBeNull();
  });
});

// ── countUnsyncedOfflineSales / isAtPendingLimit ─────────────────────────────

describe('countUnsyncedOfflineSales', () => {
  it('counts pending, syncing, failed and conflict but not synced', () => {
    const sales = [
      makeSale('pending'),
      makeSale('syncing'),
      makeSale('failed'),
      makeSale('conflict'),
      makeSale('synced'),
      makeSale('synced'),
    ];
    expect(countUnsyncedOfflineSales(sales)).toBe(4);
  });

  it('returns 0 when every sale is synced', () => {
    expect(countUnsyncedOfflineSales([makeSale('synced'), makeSale('synced')])).toBe(0);
  });
});

describe('isAtPendingLimit', () => {
  it('is false below the limit', () => {
    expect(isAtPendingLimit(MAX_PENDING_OFFLINE_SALES - 1)).toBe(false);
  });

  it('is true at and above the limit', () => {
    expect(isAtPendingLimit(MAX_PENDING_OFFLINE_SALES)).toBe(true);
    expect(isAtPendingLimit(MAX_PENDING_OFFLINE_SALES + 5)).toBe(true);
  });
});
