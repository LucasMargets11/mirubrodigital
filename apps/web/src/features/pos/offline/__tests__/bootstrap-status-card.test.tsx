/**
 * PR-OFF-02B — Offline status card + download hooks (UI).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { PosOfflineStatusCard } from '../bootstrap-status-card';
import { saveBootstrapSnapshot } from '../bootstrap-store';
import { InMemoryBootstrapStorage, __setBootstrapStorageForTests } from '../db';
import type { PosOfflineBootstrapPayload } from '../types';

const mocks = vi.hoisted(() => ({
  useEmployeeSession: vi.fn(),
  posGetOfflineBootstrap: vi.fn(),
}));

vi.mock('../../context', () => ({
  useEmployeeSession: mocks.useEmployeeSession,
}));

vi.mock('@/lib/api/pos', () => ({
  posGetOfflineBootstrap: mocks.posGetOfflineBootstrap,
}));

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
    categories: [{ id: 'cat-1', name: 'Bebidas', is_active: true }],
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
        category_id: 'cat-1',
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

function renderCard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <PosOfflineStatusCard />
    </QueryClientProvider>,
  );
}

describe('PosOfflineStatusCard', () => {
  beforeEach(() => {
    __setBootstrapStorageForTests(new InMemoryBootstrapStorage());
    mocks.useEmployeeSession.mockReturnValue({
      session: { status: 'authenticated', token: 'tok-1', mustChangePin: false },
    });
    mocks.posGetOfflineBootstrap.mockReset();
  });

  afterEach(() => {
    __setBootstrapStorageForTests(null);
    vi.clearAllMocks();
  });

  it('shows the empty state when nothing has been downloaded', async () => {
    renderCard();
    expect(
      await screen.findByText('Todavía no descargaste datos para contingencia.'),
    ).toBeInTheDocument();
  });

  it('shows last update and counts when a snapshot exists', async () => {
    await saveBootstrapSnapshot(makePayload());
    renderCard();

    expect(await screen.findByText('Última actualización')).toBeInTheDocument();
    expect(screen.getByText('Productos disponibles')).toBeInTheDocument();
    // 2 products
    expect(screen.getAllByText('2').length).toBeGreaterThan(0);
  });

  it('shows offline-disabled message when policy.enabled is false', async () => {
    await saveBootstrapSnapshot(
      makePayload({
        offline_policy: {
          enabled: false,
          mode: 'quick_sale_only',
          expires_in_hours: 24,
          supports_kitchen: false,
          supports_tables: false,
          supports_orders: false,
        },
      }),
    );
    renderCard();

    expect(
      await screen.findByText('Modo offline no habilitado para este negocio.'),
    ).toBeInTheDocument();
  });

  it('downloads and persists the snapshot on click', async () => {
    mocks.posGetOfflineBootstrap.mockResolvedValueOnce(makePayload());
    renderCard();

    await screen.findByText('Todavía no descargaste datos para contingencia.');
    fireEvent.click(screen.getByRole('button', { name: /actualizar datos offline/i }));

    await waitFor(() => {
      expect(mocks.posGetOfflineBootstrap).toHaveBeenCalledWith('tok-1');
    });
    expect(await screen.findByText('Última actualización')).toBeInTheDocument();
  });

  it('keeps prior snapshot and surfaces an error when download fails', async () => {
    await saveBootstrapSnapshot(makePayload());
    mocks.posGetOfflineBootstrap.mockRejectedValueOnce(new Error('network down'));
    renderCard();

    await screen.findByText('Última actualización');
    fireEvent.click(screen.getByRole('button', { name: /actualizar datos offline/i }));

    expect(
      await screen.findByText(/no se pudieron actualizar los datos offline/i),
    ).toBeInTheDocument();
    // Prior snapshot still visible
    expect(screen.getByText('Última actualización')).toBeInTheDocument();
  });
});
