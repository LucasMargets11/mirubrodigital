/**
 * PR-OFF-06 — OfflineSalesPanel (offline queue UX) integration tests.
 *
 * Renders the full offline panel against an in-memory queue, with mocked
 * employee session, network status and API client. Covers status counts, last
 * sync, server_id, error rendering, retry, clear-synced and the manual sync
 * button (disabled while offline).
 */

import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { OfflineSalesPanel } from '../offline-sales-panel';
import {
  InMemoryOfflineSalesStorage,
  __setOfflineSalesStorageForTests,
  listOfflineSales,
} from '../offline-sales-store';
import { __resetSyncInFlightForTests } from '../offline-sales-sync';
import type { OfflineSaleQueueItem } from '../offline-sales-types';

const mocks = vi.hoisted(() => ({
  isOnline: true,
  token: 'tok-pos' as string | null,
  posCreateSaleFromOffline: vi.fn(),
}));

vi.mock('@/features/pos/context', () => ({
  useEmployeeSession: () => ({
    session: mocks.token
      ? {
          status: 'authenticated' as const,
          token: mocks.token,
          employee: {},
          mustChangePin: false,
        }
      : { status: 'unauthenticated' as const },
  }),
}));

vi.mock('@/hooks/use-network-status', () => ({
  useNetworkStatus: () => ({
    isOnline: mocks.isOnline,
    isOffline: !mocks.isOnline,
    status: mocks.isOnline ? 'online' : 'offline',
  }),
}));

vi.mock('@/lib/api/pos', () => ({
  posCreateSaleFromOffline: (...args: unknown[]) =>
    mocks.posCreateSaleFromOffline(...args),
}));

let storage: InMemoryOfflineSalesStorage;

function makeSale(overrides: Partial<OfflineSaleQueueItem> = {}): OfflineSaleQueueItem {
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
    totals_snapshot: { subtotal: '1000.00', discount: '0.00', total: '1000.00', item_count: 1 },
    payment_snapshot: [{ method: 'cash', amount: '1000.00' }],
    source: 'pos_offline',
    offline_snapshot_generated_at: '2026-06-06T09:00:00.000Z',
    offline_snapshot_saved_at: '2026-06-06T09:30:00.000Z',
    ...overrides,
  };
}

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <OfflineSalesPanel />
    </QueryClientProvider>,
  );
  return { ...utils, queryClient };
}

beforeEach(() => {
  mocks.isOnline = true;
  mocks.token = 'tok-pos';
  mocks.posCreateSaleFromOffline.mockReset();
  mocks.posCreateSaleFromOffline.mockResolvedValue({
    sale: { id: 'srv-1' },
    duplicate: false,
    server_id: 'srv-1',
  });
  storage = new InMemoryOfflineSalesStorage();
  __setOfflineSalesStorageForTests(storage);
  __resetSyncInFlightForTests();
});

afterEach(() => {
  vi.clearAllMocks();
  __setOfflineSalesStorageForTests(null);
  __resetSyncInFlightForTests();
});

describe('OfflineSalesPanel', () => {
  it('shows counts per status', async () => {
    await storage.add(makeSale({ local_id: 'p1', status: 'pending' }));
    await storage.add(makeSale({ local_id: 'p2', status: 'pending' }));
    await storage.add(makeSale({ local_id: 'sy', status: 'synced', retryable: false, server_id: 'srv-9', synced_at: '2026-06-06T11:00:00.000Z' }));
    await storage.add(makeSale({ local_id: 'fa', status: 'failed', retryable: false, last_error: 'Stock insuficiente' }));
    await storage.add(makeSale({ local_id: 'co', status: 'conflict', retryable: false }));

    renderPanel();

    await waitFor(() => {
      expect(screen.getByTestId('offline-count-pending')).toHaveTextContent('Pendientes: 2');
    });
    expect(screen.getByTestId('offline-count-syncing')).toHaveTextContent('Sincronizando: 0');
    expect(screen.getByTestId('offline-count-synced')).toHaveTextContent('Sincronizadas: 1');
    expect(screen.getByTestId('offline-count-failed')).toHaveTextContent('Fallidas: 1');
    expect(screen.getByTestId('offline-count-conflict')).toHaveTextContent('Conflictos: 1');
  });

  it('shows the abbreviated client_order_id for each sale', async () => {
    await storage.add(
      makeSale({ local_id: 's1', client_order_id: 'abcdef12-0000-4000-8000-000000000000' }),
    );

    renderPanel();

    expect(await screen.findByText('#abcdef12')).toBeInTheDocument();
  });

  it('shows the server_id for a synced sale', async () => {
    await storage.add(
      makeSale({
        local_id: 's1',
        status: 'synced',
        retryable: false,
        server_id: 'srvabcde-0000-4000-8000-000000000000',
        synced_at: '2026-06-06T11:00:00.000Z',
      }),
    );

    renderPanel();

    const serverId = await screen.findByTestId('offline-sale-server-id');
    expect(serverId).toHaveTextContent('srvabcde');
  });

  it('shows a readable error for a failed sale', async () => {
    await storage.add(
      makeSale({
        local_id: 's1',
        status: 'failed',
        retryable: false,
        last_error: 'Stock insuficiente para el producto',
      }),
    );

    renderPanel();

    expect(
      await screen.findByText('Stock insuficiente para uno o más productos.'),
    ).toBeInTheDocument();
  });

  it('shows the last successful sync timestamp when there are synced sales', async () => {
    await storage.add(
      makeSale({
        local_id: 's1',
        status: 'synced',
        retryable: false,
        server_id: 'srv-1',
        synced_at: '2026-06-06T11:30:00.000Z',
      }),
    );

    renderPanel();

    await waitFor(() => {
      expect(screen.getByTestId('offline-last-sync')).toHaveTextContent('Última sincronización:');
    });
  });

  it('shows "Todavía no se sincronizó ninguna venta" when nothing synced', async () => {
    await storage.add(makeSale({ local_id: 'p1', status: 'pending' }));

    renderPanel();

    expect(
      await screen.findByText('Todavía no se sincronizó ninguna venta'),
    ).toBeInTheDocument();
  });

  it('"Sincronizar ahora" button triggers the sync and marks the sale synced', async () => {
    await storage.add(makeSale({ local_id: 's1' }));

    renderPanel();

    const button = await screen.findByRole('button', { name: /Sincronizar ahora/i });
    expect(mocks.posCreateSaleFromOffline).not.toHaveBeenCalled();

    fireEvent.click(button);

    await waitFor(() => {
      expect(mocks.posCreateSaleFromOffline).toHaveBeenCalledTimes(1);
    });
    expect(mocks.posCreateSaleFromOffline).toHaveBeenCalledWith(
      'tok-pos',
      expect.objectContaining({ client_order_id: expect.any(String) }),
    );

    await waitFor(async () => {
      const [stored] = await listOfflineSales(storage);
      expect(stored.status).toBe('synced');
    });
    expect(await screen.findByText('Ventas sincronizadas correctamente')).toBeInTheDocument();
  });

  it('"Reintentar" on a retryable failed sale triggers the sync', async () => {
    await storage.add(
      makeSale({
        local_id: 's1',
        status: 'failed',
        retryable: true,
        last_error: 'Error del servidor al sincronizar.',
      }),
    );

    renderPanel();

    const retry = await screen.findByRole('button', { name: 'Reintentar' });
    fireEvent.click(retry);

    await waitFor(() => {
      expect(mocks.posCreateSaleFromOffline).toHaveBeenCalledTimes(1);
    });
  });

  it('disables the sync button while offline with a "Sin conexión" label', async () => {
    mocks.isOnline = false;
    await storage.add(makeSale({ local_id: 's1' }));

    renderPanel();

    const button = await screen.findByRole('button', { name: 'Sin conexión' });
    expect(button).toBeDisabled();
    expect(mocks.posCreateSaleFromOffline).not.toHaveBeenCalled();
  });

  it('"Limpiar historial" removes synced, failed and conflict but keeps pending', async () => {
    mocks.isOnline = false; // stay offline so no sync run fires
    await storage.add(makeSale({ local_id: 'p1', status: 'pending' }));
    await storage.add(makeSale({ local_id: 'fa', status: 'failed', retryable: false, last_error: 'x' }));
    await storage.add(makeSale({ local_id: 'co', status: 'conflict', retryable: false }));
    await storage.add(
      makeSale({ local_id: 'sy', status: 'synced', retryable: false, server_id: 'srv-1', synced_at: '2026-06-06T11:00:00.000Z' }),
    );

    renderPanel();

    const clearButton = await screen.findByRole('button', { name: /Limpiar historial/i });
    fireEvent.click(clearButton);

    await waitFor(async () => {
      const remaining = await listOfflineSales(storage);
      expect(remaining.map((s) => s.local_id)).toEqual(['p1']);
    });
    // Synced, failed and conflict are gone; only the pending sale remains.
    const remaining = await listOfflineSales(storage);
    expect(remaining.some((s) => s.status === 'synced')).toBe(false);
    expect(remaining.some((s) => s.status === 'failed')).toBe(false);
    expect(remaining.some((s) => s.status === 'conflict')).toBe(false);
    expect(remaining.some((s) => s.status === 'pending')).toBe(true);
  });

  it('after "Limpiar historial" the failed sale error no longer shows in the panel', async () => {
    mocks.isOnline = false;
    await storage.add(makeSale({ local_id: 'p1', status: 'pending' }));
    await storage.add(
      makeSale({
        local_id: 'fa',
        status: 'failed',
        retryable: false,
        last_error: 'Stock insuficiente para el producto',
      }),
    );

    renderPanel();

    // The error is visible before clearing.
    expect(
      await screen.findByText('Stock insuficiente para uno o más productos.'),
    ).toBeInTheDocument();

    fireEvent.click(await screen.findByRole('button', { name: /Limpiar historial/i }));

    // The error row disappears, the pending sale survives.
    await waitFor(() => {
      expect(screen.queryByTestId('offline-sale-error')).not.toBeInTheDocument();
    });
    const remaining = await listOfflineSales(storage);
    expect(remaining.map((s) => s.local_id)).toEqual(['p1']);
  });

  it('"Reintentar errores" returns retryable failures to pending and clears the error', async () => {
    mocks.isOnline = false; // stay offline so no sync run fires after reset
    await storage.add(
      makeSale({ local_id: 'fa', status: 'failed', retryable: true, last_error: 'Sin conexión' }),
    );
    await storage.add(
      makeSale({ local_id: 'nf', status: 'failed', retryable: false, last_error: 'Stock insuficiente' }),
    );
    await storage.add(makeSale({ local_id: 'co', status: 'conflict', retryable: false, last_error: 'dup' }));

    renderPanel();

    const retryButton = await screen.findByRole('button', { name: /Reintentar errores/i });
    fireEvent.click(retryButton);

    await waitFor(async () => {
      const remaining = await listOfflineSales(storage);
      expect(remaining.find((s) => s.local_id === 'fa')!.status).toBe('pending');
    });

    const remaining = await listOfflineSales(storage);
    // Retryable failed → pending, error cleared.
    const recovered = remaining.find((s) => s.local_id === 'fa')!;
    expect(recovered.status).toBe('pending');
    expect(recovered.last_error).toBeNull();
    // Non-retryable failed and conflict are left untouched. Nothing deleted.
    expect(remaining.find((s) => s.local_id === 'nf')!.status).toBe('failed');
    expect(remaining.find((s) => s.local_id === 'co')!.status).toBe('conflict');
    expect(remaining).toHaveLength(3);
  });

  it('does not show "Reintentar errores" when there are no retryable failures', async () => {
    await storage.add(makeSale({ local_id: 'p1', status: 'pending' }));
    await storage.add(makeSale({ local_id: 'co', status: 'conflict', retryable: false }));
    await storage.add(makeSale({ local_id: 'nf', status: 'failed', retryable: false, last_error: 'x' }));

    renderPanel();

    await screen.findByTestId('offline-sync-status');
    expect(
      screen.queryByRole('button', { name: /Reintentar errores/i }),
    ).not.toBeInTheDocument();
  });

  it('auto-syncs once when the device transitions back online', async () => {
    mocks.isOnline = false;
    await storage.add(makeSale({ local_id: 's1' }));

    const { rerender, queryClient } = renderPanel();
    await screen.findByTestId('offline-sync-status');
    expect(mocks.posCreateSaleFromOffline).not.toHaveBeenCalled();

    // Reconnect.
    mocks.isOnline = true;
    rerender(
      <QueryClientProvider client={queryClient}>
        <OfflineSalesPanel />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(mocks.posCreateSaleFromOffline).toHaveBeenCalledTimes(1);
    });
  });
});
