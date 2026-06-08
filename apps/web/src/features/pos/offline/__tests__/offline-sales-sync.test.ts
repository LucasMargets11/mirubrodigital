/**
 * PR-OFF-05 — Offline sale sync engine unit tests.
 *
 * Pure tests against {@link syncOfflineSales} with an in-memory storage adapter
 * and an injected submit function. No React, no network, no token.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  InMemoryOfflineSalesStorage,
  listOfflineSales,
} from '../offline-sales-store';
import {
  classifySyncError,
  isSyncableSale,
  syncOfflineSales,
  __resetSyncInFlightForTests,
  type OfflineSaleSubmit,
} from '../offline-sales-sync';
import type {
  OfflineSaleQueueItem,
  OfflineSaleStatus,
  OfflineSaleSyncResult,
} from '../offline-sales-types';

function makeSale(
  overrides: Partial<OfflineSaleQueueItem> = {},
): OfflineSaleQueueItem {
  const clientOrderId =
    overrides.client_order_id ?? `00000000-0000-4000-8000-${Math.random().toString(16).slice(2, 14).padEnd(12, '0')}`;
  return {
    local_id: overrides.local_id ?? clientOrderId,
    client_order_id: clientOrderId,
    business_id: 'biz-1',
    employee_id: 'emp-1',
    employee_code: '0001',
    cash_session_id: 'cash-1',
    created_at: '2026-06-06T10:00:00.000Z',
    updated_at: '2026-06-06T10:00:00.000Z',
    status: 'pending',
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
      note: 'Venta offline',
      source: 'pos_offline',
    },
    totals_snapshot: {
      subtotal: '1000.00',
      discount: '0.00',
      total: '1000.00',
      item_count: 1,
    },
    payment_snapshot: [{ method: 'cash', amount: '1000.00' }],
    source: 'pos_offline',
    offline_snapshot_generated_at: '2026-06-06T09:00:00.000Z',
    offline_snapshot_saved_at: '2026-06-06T09:30:00.000Z',
    ...overrides,
  };
}

function okResult(serverId: string, duplicate = false): OfflineSaleSyncResult {
  return { sale: { id: serverId }, duplicate, server_id: serverId };
}

class HttpError extends Error {
  status: number;
  constructor(status: number, message = 'http error') {
    super(message);
    this.status = status;
  }
}

const NOW = () => '2026-06-06T12:00:00.000Z';

let storage: InMemoryOfflineSalesStorage;

beforeEach(() => {
  storage = new InMemoryOfflineSalesStorage();
  __resetSyncInFlightForTests();
});

afterEach(() => {
  __resetSyncInFlightForTests();
});

describe('classifySyncError', () => {
  it('classifies a network error (no status) as retryable, stops the loop', () => {
    const c = classifySyncError(new Error('Failed to fetch'));
    expect(c.kind).toBe('network');
    expect(c.status).toBe('pending');
    expect(c.retryable).toBe(true);
    expect(c.stopLoop).toBe(true);
  });

  it('classifies 400 as non-retryable failed, continues the loop', () => {
    const c = classifySyncError(new HttpError(400));
    expect(c.kind).toBe('validation');
    expect(c.status).toBe('failed');
    expect(c.retryable).toBe(false);
    expect(c.stopLoop).toBe(false);
  });

  it('classifies 409 as conflict', () => {
    const c = classifySyncError(new HttpError(409));
    expect(c.kind).toBe('conflict');
    expect(c.status).toBe('conflict');
    expect(c.stopLoop).toBe(false);
  });

  it('classifies 401/403 as auth failed and stops the loop', () => {
    for (const status of [401, 403]) {
      const c = classifySyncError(new HttpError(status));
      expect(c.kind).toBe('auth');
      expect(c.status).toBe('failed');
      expect(c.stopLoop).toBe(true);
      expect(c.message).toMatch(/no está autorizada/i);
    }
  });

  it('classifies 500 as retryable server failure and stops the loop', () => {
    const c = classifySyncError(new HttpError(500));
    expect(c.kind).toBe('server');
    expect(c.status).toBe('failed');
    expect(c.retryable).toBe(true);
    expect(c.stopLoop).toBe(true);
  });
});

describe('isSyncableSale', () => {
  it('includes pending sales', () => {
    expect(isSyncableSale(makeSale({ status: 'pending' }))).toBe(true);
  });

  it('includes retryable failed sales', () => {
    expect(isSyncableSale(makeSale({ status: 'failed', retryable: true }))).toBe(true);
  });

  it('excludes non-retryable failed, synced, conflict and syncing sales', () => {
    expect(isSyncableSale(makeSale({ status: 'failed', retryable: false }))).toBe(false);
    expect(isSyncableSale(makeSale({ status: 'synced' }))).toBe(false);
    expect(isSyncableSale(makeSale({ status: 'conflict' }))).toBe(false);
    expect(isSyncableSale(makeSale({ status: 'syncing' }))).toBe(false);
  });

  it('excludes sales with no items, no payments or zero total', () => {
    const noItems = makeSale();
    noItems.sale_payload.items = [];
    expect(isSyncableSale(noItems)).toBe(false);

    const zeroTotal = makeSale();
    zeroTotal.totals_snapshot.total = '0.00';
    expect(isSyncableSale(zeroTotal)).toBe(false);
  });
});

describe('syncOfflineSales', () => {
  it('does not sync when offline and never calls submit', async () => {
    await storage.add(makeSale());
    const submit = vi.fn<OfflineSaleSubmit>();

    const result = await syncOfflineSales({ storage, submit, isOnline: false });

    expect(result.ran).toBe(false);
    expect(submit).not.toHaveBeenCalled();
  });

  it('submits a pending sale with its client_order_id and payload', async () => {
    const sale = makeSale({ client_order_id: '11111111-1111-4111-8111-111111111111' });
    await storage.add(sale);
    const submit = vi.fn<OfflineSaleSubmit>(async () => okResult('srv-1'));

    await syncOfflineSales({ storage, submit, isOnline: true, now: NOW });

    expect(submit).toHaveBeenCalledTimes(1);
    expect(submit).toHaveBeenCalledWith(sale.sale_payload);
    expect(submit.mock.calls[0][0].client_order_id).toBe(
      '11111111-1111-4111-8111-111111111111',
    );
  });

  it('marks the sale synced and stores server_id + synced_at on success', async () => {
    await storage.add(makeSale({ local_id: 's1' }));
    const submit = vi.fn<OfflineSaleSubmit>(async () => okResult('srv-99', false));

    const result = await syncOfflineSales({ storage, submit, isOnline: true, now: NOW });

    expect(result.synced).toBe(1);
    const [stored] = await listOfflineSales(storage);
    expect(stored.status).toBe('synced');
    expect(stored.server_id).toBe('srv-99');
    expect(stored.synced_at).toBe('2026-06-06T12:00:00.000Z');
    expect(stored.duplicate_ack).toBe(false);
  });

  it('marks the sale synced with duplicate_ack when the server reports a duplicate', async () => {
    await storage.add(makeSale({ local_id: 's1' }));
    const submit = vi.fn<OfflineSaleSubmit>(async () => okResult('srv-dup', true));

    const result = await syncOfflineSales({ storage, submit, isOnline: true, now: NOW });

    expect(result.synced).toBe(1);
    const [stored] = await listOfflineSales(storage);
    expect(stored.status).toBe('synced');
    expect(stored.server_id).toBe('srv-dup');
    expect(stored.duplicate_ack).toBe(true);
  });

  it('leaves a sale retryable (pending) on a network error and stops the loop', async () => {
    await storage.add(makeSale({ local_id: 's1', created_at: '2026-06-06T10:00:00.000Z' }));
    await storage.add(makeSale({ local_id: 's2', created_at: '2026-06-06T11:00:00.000Z' }));
    const submit = vi.fn<OfflineSaleSubmit>(async () => {
      throw new Error('Failed to fetch');
    });

    const result = await syncOfflineSales({ storage, submit, isOnline: true, now: NOW });

    // Only the first (oldest) sale is attempted — the loop is cut.
    expect(submit).toHaveBeenCalledTimes(1);
    expect(result.stoppedOnError).toBe(true);
    const byId = Object.fromEntries((await listOfflineSales(storage)).map((s) => [s.local_id, s]));
    expect(byId.s1.status).toBe('pending');
    expect(byId.s1.retryable).toBe(true);
    expect(byId.s1.sync_attempts).toBe(1);
    expect(byId.s2.status).toBe('pending'); // never touched
    expect(byId.s2.sync_attempts).toBe(0);
  });

  it('marks a sale failed (non-retryable) on 400 and continues with the next', async () => {
    await storage.add(makeSale({ local_id: 's1', created_at: '2026-06-06T10:00:00.000Z' }));
    await storage.add(makeSale({ local_id: 's2', created_at: '2026-06-06T11:00:00.000Z' }));
    const submit = vi
      .fn<OfflineSaleSubmit>()
      .mockRejectedValueOnce(new HttpError(400, 'bad data'))
      .mockResolvedValueOnce(okResult('srv-2'));

    const result = await syncOfflineSales({ storage, submit, isOnline: true, now: NOW });

    expect(submit).toHaveBeenCalledTimes(2);
    expect(result.failed).toBe(1);
    expect(result.synced).toBe(1);
    const byId = Object.fromEntries((await listOfflineSales(storage)).map((s) => [s.local_id, s]));
    expect(byId.s1.status).toBe('failed');
    expect(byId.s1.retryable).toBe(false);
    expect(byId.s2.status).toBe('synced');
  });

  it('marks a sale conflict on 409', async () => {
    await storage.add(makeSale({ local_id: 's1' }));
    const submit = vi.fn<OfflineSaleSubmit>(async () => {
      throw new HttpError(409, 'conflict');
    });

    const result = await syncOfflineSales({ storage, submit, isOnline: true, now: NOW });

    expect(result.conflicts).toBe(1);
    const [stored] = await listOfflineSales(storage);
    expect(stored.status).toBe('conflict');
  });

  it('does not sync already synced or conflict sales', async () => {
    await storage.add(makeSale({ local_id: 'synced', status: 'synced', retryable: false }));
    await storage.add(makeSale({ local_id: 'conflict', status: 'conflict', retryable: false }));
    const submit = vi.fn<OfflineSaleSubmit>(async () => okResult('x'));

    const result = await syncOfflineSales({ storage, submit, isOnline: true, now: NOW });

    expect(submit).not.toHaveBeenCalled();
    expect(result.attempted).toBe(0);
  });

  it('processes sales oldest-first (created_at ASC)', async () => {
    await storage.add(makeSale({ local_id: 'newer', client_order_id: '22222222-2222-4222-8222-222222222222', created_at: '2026-06-06T11:00:00.000Z' }));
    await storage.add(makeSale({ local_id: 'older', client_order_id: '11111111-1111-4111-8111-111111111111', created_at: '2026-06-06T10:00:00.000Z' }));
    const seen: string[] = [];
    const submit = vi.fn<OfflineSaleSubmit>(async (payload) => {
      seen.push(payload.client_order_id);
      return okResult(payload.client_order_id);
    });

    await syncOfflineSales({ storage, submit, isOnline: true, now: NOW });

    expect(seen).toEqual([
      '11111111-1111-4111-8111-111111111111',
      '22222222-2222-4222-8222-222222222222',
    ]);
  });

  it('never changes client_order_id across attempts', async () => {
    const sale = makeSale({ local_id: 's1', client_order_id: '33333333-3333-4333-8333-333333333333' });
    await storage.add(sale);
    const submit = vi
      .fn<OfflineSaleSubmit>()
      .mockRejectedValueOnce(new Error('network'));

    await syncOfflineSales({ storage, submit, isOnline: true, now: NOW });
    // Second run after the transient failure.
    submit.mockResolvedValueOnce(okResult('srv-3'));
    await syncOfflineSales({ storage, submit, isOnline: true, now: NOW });

    const [stored] = await listOfflineSales(storage);
    expect(stored.client_order_id).toBe('33333333-3333-4333-8333-333333333333');
    expect(stored.sale_payload.client_order_id).toBe('33333333-3333-4333-8333-333333333333');
    expect(stored.status).toBe('synced');
    expect(submit.mock.calls.every((c) => c[0].client_order_id === '33333333-3333-4333-8333-333333333333')).toBe(true);
  });

  it('attempts the second sale when the first succeeds', async () => {
    await storage.add(makeSale({ local_id: 's1', client_order_id: '11111111-1111-4111-8111-111111111111', created_at: '2026-06-06T10:00:00.000Z' }));
    await storage.add(makeSale({ local_id: 's2', client_order_id: '22222222-2222-4222-8222-222222222222', created_at: '2026-06-06T11:00:00.000Z' }));
    const submit = vi.fn<OfflineSaleSubmit>(async (p) => okResult(p.client_order_id));

    const result = await syncOfflineSales({ storage, submit, isOnline: true, now: NOW });

    expect(submit).toHaveBeenCalledTimes(2);
    expect(result.synced).toBe(2);
  });

  it('skips when a run is already in flight', async () => {
    await storage.add(makeSale());
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const submit = vi.fn<OfflineSaleSubmit>(async (p) => {
      await gate;
      return okResult(p.client_order_id);
    });

    const first = syncOfflineSales({ storage, submit, isOnline: true, now: NOW });
    const second = await syncOfflineSales({ storage, submit, isOnline: true, now: NOW });

    expect(second.ran).toBe(false);
    release();
    await first;
    expect(submit).toHaveBeenCalledTimes(1);
  });

  it('only ever calls submit — no other side-effect channels', async () => {
    await storage.add(makeSale());
    const submit = vi.fn<OfflineSaleSubmit>(async (p) => okResult(p.client_order_id));

    await syncOfflineSales({ storage, submit, isOnline: true, now: NOW });

    // The engine's only outbound dependency is `submit`.
    expect(submit).toHaveBeenCalledTimes(1);
    const statuses: OfflineSaleStatus[] = (await listOfflineSales(storage)).map((s) => s.status);
    expect(statuses).toEqual(['synced']);
  });
});
