/**
 * PR-OFF-06 — unit tests for the offline-sale presentation helpers.
 */

import { describe, expect, it } from 'vitest';

import {
  describeOfflineSaleError,
  describeOfflineSalePayments,
  paymentMethodLabel,
} from '../offline-sale-error';
import type { OfflineSaleQueueItem } from '../offline-sales-types';

function makeSale(overrides: Partial<OfflineSaleQueueItem> = {}): OfflineSaleQueueItem {
  return {
    local_id: 'l1',
    client_order_id: '00000000-0000-4000-8000-000000000000',
    business_id: 'biz-1',
    employee_id: 'emp-1',
    employee_code: '0001',
    cash_session_id: 'cash-1',
    created_at: '2026-06-06T10:00:00.000Z',
    updated_at: '2026-06-06T10:00:00.000Z',
    status: 'failed',
    sync_attempts: 1,
    last_error: null,
    retryable: true,
    server_id: null,
    synced_at: null,
    duplicate_ack: false,
    sale_payload: {
      client_order_id: '00000000-0000-4000-8000-000000000000',
      items: [{ product: 'p', quantity: '1', unit_price: '1000.00' }],
      payments: [{ method: 'cash', amount: '1000.00' }],
      note: '',
      source: 'pos_offline',
    },
    totals_snapshot: { subtotal: '1000.00', discount: '0.00', total: '1000.00', item_count: 1 },
    payment_snapshot: [{ method: 'cash', amount: '1000.00' }],
    source: 'pos_offline',
    offline_snapshot_generated_at: '2026-06-06T09:00:00.000Z',
    offline_snapshot_saved_at: '2026-06-06T09:30:00.000Z',
    ...overrides,
  };
}

describe('paymentMethodLabel', () => {
  it('maps known codes to Spanish labels', () => {
    expect(paymentMethodLabel('cash')).toBe('Efectivo');
    expect(paymentMethodLabel('transfer')).toBe('Transferencia');
    expect(paymentMethodLabel('card')).toBe('Tarjeta');
    expect(paymentMethodLabel('other')).toBe('Otro');
  });
});

describe('describeOfflineSalePayments', () => {
  it('returns a dash when empty', () => {
    expect(describeOfflineSalePayments([])).toBe('—');
  });

  it('joins distinct method labels', () => {
    expect(
      describeOfflineSalePayments([
        { method: 'cash', amount: '500.00' },
        { method: 'card', amount: '500.00' },
        { method: 'cash', amount: '100.00' },
      ]),
    ).toBe('Efectivo + Tarjeta');
  });
});

describe('describeOfflineSaleError', () => {
  it('returns null for non-failed/non-conflict sales', () => {
    expect(describeOfflineSaleError(makeSale({ status: 'pending' }))).toBeNull();
    expect(describeOfflineSaleError(makeSale({ status: 'synced' }))).toBeNull();
    expect(describeOfflineSaleError(makeSale({ status: 'syncing' }))).toBeNull();
  });

  it('returns a conflict message for conflict sales', () => {
    expect(describeOfflineSaleError(makeSale({ status: 'conflict' }))).toContain('Conflicto');
  });

  it('normalises auth errors', () => {
    expect(
      describeOfflineSaleError(makeSale({ last_error: 'La sesión POS ya no está autorizada.' })),
    ).toContain('Sesión no autorizada');
  });

  it('normalises stock errors', () => {
    expect(
      describeOfflineSaleError(makeSale({ last_error: 'Stock insuficiente' })),
    ).toContain('Stock insuficiente');
  });

  it('normalises closed-cash errors', () => {
    expect(
      describeOfflineSaleError(makeSale({ last_error: 'La caja está cerrada' })),
    ).toContain('caja está cerrada');
  });

  it('normalises network errors', () => {
    expect(
      describeOfflineSaleError(makeSale({ last_error: 'Sin conexión al sincronizar' })),
    ).toContain('Error de red');
  });

  it('falls back to a generic message when last_error is empty', () => {
    expect(describeOfflineSaleError(makeSale({ last_error: null }))).toBe(
      'Error desconocido al sincronizar.',
    );
  });

  it('passes through an unknown raw message', () => {
    expect(
      describeOfflineSaleError(makeSale({ last_error: 'Algo raro pasó' })),
    ).toBe('Algo raro pasó');
  });
});
