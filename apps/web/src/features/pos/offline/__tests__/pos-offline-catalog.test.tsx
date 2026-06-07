/**
 * PR-OFF-03 — PosNewSalePage offline catalog integration.
 *
 * Verifies the quick-sale screen uses the locally-persisted snapshot when the
 * device is offline, blocks sale confirmation, and keeps the online flow intact.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { PosNewSalePage } from '@/features/pos/components/PosNewSalePage';
import type { PosProduct } from '@/types/pos-cash';
import type { StoredPosOfflineBootstrap } from '../types';
import {
  InMemoryOfflineSalesStorage,
  __setOfflineSalesStorageForTests,
  listOfflineSales,
} from '../offline-sales-store';
import { isValidClientOrderId } from '../offline-sale-id';

let salesStore = new InMemoryOfflineSalesStorage();

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <PosNewSalePage />
    </QueryClientProvider>,
  );
}

const mocks = vi.hoisted(() => ({
  isOffline: false,
  snapshot: null as StoredPosOfflineBootstrap | null,
  snapshotLoading: false,
  routerPush: vi.fn(),
  createSaleMutateAsync: vi.fn(),
  createCounterOrderMutateAsync: vi.fn(),
  operationSettings: {
    tables_enabled: false,
    kitchen_enabled: false,
    counter_orders_enabled: false,
    pos_quick_sale_enabled: true,
    allow_pickup_orders: false,
    allow_dine_in_orders: false,
    allow_delivery_orders: false,
    default_pos_mode: 'quick_sale' as 'quick_sale' | 'kitchen_order',
  },
  handleError: vi.fn((err: unknown) =>
    err instanceof Error ? err.message : 'Error inesperado.',
  ),
  usePosCategories: vi.fn(() => ({ data: { results: [], count: 0 }, isLoading: false })),
  usePosBrowseProducts: vi.fn(() => ({ data: { results: [], count: 0 }, isFetching: false })),
  useUnifiedProductSearch: vi.fn(() => ({ results: [], isLoading: false })),
  usePosProducts: vi.fn(() => ({ data: { results: [], count: 0 }, isLoading: false })),
}));

const onlineProductFixture: PosProduct = {
  id: 'online-1',
  name: 'Producto online',
  sku: 'ON-1',
  price: '1000.00',
  stock_quantity: '5.00',
  stock_min: '1.00',
  category_id: 'cat-1',
  is_active: true,
};

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.routerPush }),
}));

vi.mock('@/features/pos/context', () => ({
  useEmployeeSession: () => ({
    session: {
      status: 'authenticated' as const,
      token: 'tok-pos',
      employee: {
        id: 'emp-1',
        employee_code: 'EMP-001',
        display_name: 'Caja',
        full_name: 'Caja Uno',
        role_type: 'cashier' as const,
        branch: 1,
        branch_name: 'Centro',
        status: 'active' as const,
        must_change_pin: false,
        business_id: 1,
        business_name: 'Demo',
      },
      mustChangePin: false,
    },
  }),
}));

vi.mock('@/features/pos/cash-hooks', () => ({
  usePosCreateSale: () => ({ mutateAsync: mocks.createSaleMutateAsync, isPending: false }),
  usePosCreateCounterOrder: () => ({
    mutateAsync: mocks.createCounterOrderMutateAsync,
    isPending: false,
  }),
  usePosErrorHandler: () => mocks.handleError,
  usePosCategories: () => mocks.usePosCategories(),
  usePosBrowseProducts: () => mocks.usePosBrowseProducts(),
  useUnifiedProductSearch: () => mocks.useUnifiedProductSearch(),
  usePosProducts: () => mocks.usePosProducts(),
}));

vi.mock('@/features/resto/hooks', () => ({
  useRestaurantOperationSettings: () => ({
    data: mocks.operationSettings,
    isLoading: false,
    isError: false,
  }),
  getEffectiveRestaurantOperationSettings: (value: unknown) => value,
}));

vi.mock('@/features/pos/offline/pos-operation-settings', () => ({
  usePosOperationSettings: () => mocks.operationSettings,
}));

vi.mock('@/hooks/use-network-status', () => ({
  useNetworkStatus: () => ({
    isOnline: !mocks.isOffline,
    isOffline: mocks.isOffline,
    status: mocks.isOffline ? 'offline' : 'online',
  }),
}));

vi.mock('@/features/pos/offline/bootstrap-hooks', () => ({
  usePosOfflineSnapshot: () => ({
    data: mocks.snapshot,
    isLoading: mocks.snapshotLoading,
  }),
}));

// Online catalog panel: replaced with a simple "add fixture" button so we can
// assert it is rendered online and NOT rendered offline.
vi.mock('@/features/pos/components/ProductCatalogPanel', () => ({
  ProductCatalogPanel: ({ onAdd }: { onAdd: (p: PosProduct) => void }) => (
    <button type="button" onClick={() => onAdd(onlineProductFixture)}>
      Agregar producto online
    </button>
  ),
}));

vi.mock('@/features/pos/components/ProductSearchPanel', () => ({
  ProductSearchPanel: () => <div data-testid="product-search-panel" />,
}));

vi.mock('@/features/pos/components/SaleItemsPanel', () => ({
  SaleItemsPanel: ({ items }: { items: Array<{ product: PosProduct; quantity: number }> }) => (
    <div data-testid="cart-state">
      {items.length === 0 ? 'carrito-vacio' : `items:${items.length}:${items[0]?.product.name}`}
    </div>
  ),
}));

vi.mock('@/features/pos/components/CustomerPanel', () => ({
  CustomerPanel: () => <div data-testid="customer-panel" />,
}));

vi.mock('@/features/pos/components/DiscountPanel', () => ({
  DiscountPanel: () => <div data-testid="discount-panel" />,
}));

vi.mock('@/features/pos/components/SplitPaymentPanel', () => ({
  createPaymentLine: () => ({
    id: 'pl-1',
    method: 'efectivo',
    amount: '',
    reference: '',
    isAutoAmount: true,
  }),
  toApiPaymentLineMethod: () => 'cash',
  SplitPaymentPanel: () => <div data-testid="split-payment-panel" />,
}));

vi.mock('@/features/pos/components/SaleSummaryCard', () => ({
  SaleSummaryCard: (props: {
    confirmLabel?: string;
    helperText?: string;
    error: string;
    successMsg?: string;
    disabled: boolean;
    isPending: boolean;
    onConfirm: () => void;
  }) => (
    <div>
      {props.helperText ? <div data-testid="summary-helper">{props.helperText}</div> : null}
      {props.successMsg ? <div role="status">{props.successMsg}</div> : null}
      {props.error ? <div role="alert">{props.error}</div> : null}
      <button
        type="button"
        onClick={props.onConfirm}
        disabled={props.disabled || props.isPending}
      >
        {props.confirmLabel}
      </button>
    </div>
  ),
}));

function makeSnapshot(
  overrides: Partial<StoredPosOfflineBootstrap> = {},
): StoredPosOfflineBootstrap {
  // Use timestamps relative to "now" so the PR-OFF-07 snapshot-expiry guard
  // keeps the snapshot fresh regardless of the wall clock when tests run.
  const now = Date.now();
  return {
    bootstrap_version: 1,
    generated_at: new Date(now - 30 * 60 * 1000).toISOString(),
    saved_at: new Date(now - 25 * 60 * 1000).toISOString(),
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
      {
        id: 'prod-pizza',
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

describe('PosNewSalePage offline catalog (PR-OFF-03)', () => {
  beforeEach(() => {
    mocks.isOffline = false;
    mocks.snapshot = null;
    mocks.snapshotLoading = false;
    mocks.routerPush.mockReset();
    mocks.createSaleMutateAsync.mockReset();
    mocks.createCounterOrderMutateAsync.mockReset();
    mocks.operationSettings = {
      tables_enabled: false,
      kitchen_enabled: false,
      counter_orders_enabled: false,
      pos_quick_sale_enabled: true,
      allow_pickup_orders: false,
      allow_dine_in_orders: false,
      allow_delivery_orders: false,
      default_pos_mode: 'quick_sale',
    };
    salesStore = new InMemoryOfflineSalesStorage();
    __setOfflineSalesStorageForTests(salesStore);
    mocks.createSaleMutateAsync.mockResolvedValue({
      sale: {
        id: 'sale-1',
        number: 17,
        status: 'completed',
        status_label: 'Completada',
        payment_method: 'cash',
        payment_method_label: 'Efectivo',
        total: '1000.00',
        subtotal: '1000.00',
        discount: '0.00',
        notes: '',
        cash_session_id: 'cash-1',
        created_at: '2026-06-06T00:00:00Z',
      },
    });
    mocks.usePosBrowseProducts.mockClear();
    mocks.useUnifiedProductSearch.mockClear();
    mocks.usePosProducts.mockClear();
  });

  afterEach(() => {
    vi.clearAllMocks();
    __setOfflineSalesStorageForTests(null);
  });

  it('online: renders the online catalog panel (not offline)', () => {
    mocks.isOffline = false;
    renderPage();

    expect(screen.getByRole('button', { name: 'Agregar producto online' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Catálogo offline')).not.toBeInTheDocument();
  });

  it('offline with snapshot: shows products from the snapshot', () => {
    mocks.isOffline = true;
    mocks.snapshot = makeSnapshot();
    renderPage();

    expect(screen.getByText('Cerveza')).toBeInTheDocument();
    expect(screen.getByText('Pizza')).toBeInTheDocument();
    expect(screen.getByText(/Usando datos offline guardados/i)).toBeInTheDocument();
    // Online catalog panel must not be rendered.
    expect(
      screen.queryByRole('button', { name: 'Agregar producto online' }),
    ).not.toBeInTheDocument();
  });

  it('offline without snapshot: shows the no-data message', () => {
    mocks.isOffline = true;
    mocks.snapshot = null;
    renderPage();

    expect(
      screen.getByText(/No hay datos offline descargados/i),
    ).toBeInTheDocument();
  });

  it('offline with policy disabled: shows offline-not-enabled message', () => {
    mocks.isOffline = true;
    mocks.snapshot = makeSnapshot({
      offline_policy: {
        enabled: false,
        mode: 'quick_sale_only',
        expires_in_hours: 24,
        supports_kitchen: false,
        supports_tables: false,
        supports_orders: false,
      },
    });
    renderPage();

    expect(
      screen.getByText('Modo offline no habilitado para este negocio.'),
    ).toBeInTheDocument();
  });

  it('offline: lets the user add a snapshot product to the cart', () => {
    mocks.isOffline = true;
    mocks.snapshot = makeSnapshot();
    renderPage();

    fireEvent.click(
      screen.getByRole('button', { name: /Agregar Cerveza al carrito/i }),
    );

    expect(screen.getByTestId('cart-state').textContent).toBe('items:1:Cerveza');
  });

  // ── PR-OFF-04: offline sale capture ────────────────────────────────────────

  it('offline: confirm button switches to "Guardar venta offline"', () => {
    mocks.isOffline = true;
    mocks.snapshot = makeSnapshot();
    renderPage();

    expect(
      screen.getByRole('button', { name: 'Guardar venta offline' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Cobrar venta' }),
    ).not.toBeInTheDocument();
  });

  it('offline: saves the sale to the local queue without calling the backend', async () => {
    mocks.isOffline = true;
    mocks.snapshot = makeSnapshot();
    renderPage();

    fireEvent.click(
      screen.getByRole('button', { name: /Agregar Cerveza al carrito/i }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Guardar venta offline' }));

    await vi.waitFor(async () => {
      const queued = await listOfflineSales(salesStore);
      expect(queued).toHaveLength(1);
    });

    const [sale] = await listOfflineSales(salesStore);
    expect(sale.status).toBe('pending');
    expect(isValidClientOrderId(sale.client_order_id)).toBe(true);
    expect(sale.sale_payload.items).toEqual([
      { product: 'prod-cerveza', quantity: '1', unit_price: '1000.00' },
    ]);
    expect(sale.totals_snapshot.total).toBe('1000.00');
    expect(sale.payment_snapshot).toEqual([{ method: 'cash', amount: '1000.00' }]);

    // No backend sale was created.
    expect(mocks.createSaleMutateAsync).not.toHaveBeenCalled();

    // Success feedback + cart cleared.
    expect(
      await screen.findByText('Venta guardada para sincronizar.'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('cart-state').textContent).toBe('carrito-vacio');
  });

  it('offline: shows the pending sales counter after saving', async () => {
    mocks.isOffline = true;
    mocks.snapshot = makeSnapshot();
    renderPage();

    fireEvent.click(
      screen.getByRole('button', { name: /Agregar Cerveza al carrito/i }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Guardar venta offline' }));

    expect(await screen.findByTestId('offline-pending-count')).toHaveTextContent(
      'Ventas pendientes: 1',
    );
  });

  it('offline: blocks saving when the business requires a customer', async () => {
    mocks.isOffline = true;
    mocks.snapshot = makeSnapshot({
      commercial_settings: {
        allow_sell_without_stock: true,
        block_sales_if_no_open_cash_session: false,
        require_customer_for_sales: true,
      },
    });
    renderPage();

    fireEvent.click(
      screen.getByRole('button', { name: /Agregar Cerveza al carrito/i }),
    );

    expect(screen.getByTestId('summary-helper').textContent).toMatch(
      /requiere cliente/i,
    );
    expect(
      screen.getByRole('button', { name: 'Guardar venta offline' }),
    ).toBeDisabled();
    expect(await listOfflineSales(salesStore)).toHaveLength(0);
  });

  it('offline: blocks saving when no open cash session is in the snapshot', async () => {
    mocks.isOffline = true;
    mocks.snapshot = makeSnapshot({
      cash_session: null,
      commercial_settings: {
        allow_sell_without_stock: true,
        block_sales_if_no_open_cash_session: true,
        require_customer_for_sales: false,
      },
    });
    renderPage();

    fireEvent.click(
      screen.getByRole('button', { name: /Agregar Cerveza al carrito/i }),
    );

    expect(screen.getByTestId('summary-helper').textContent).toMatch(/caja abierta/i);
    expect(
      screen.getByRole('button', { name: 'Guardar venta offline' }),
    ).toBeDisabled();
    expect(await listOfflineSales(salesStore)).toHaveLength(0);
  });

  it('offline: does not call the online product API hooks', () => {
    mocks.isOffline = true;
    mocks.snapshot = makeSnapshot();
    renderPage();

    expect(mocks.usePosBrowseProducts).not.toHaveBeenCalled();
    expect(mocks.useUnifiedProductSearch).not.toHaveBeenCalled();
    expect(mocks.usePosProducts).not.toHaveBeenCalled();
  });

  it('back online: the online confirm flow still works', async () => {
    mocks.isOffline = false;
    renderPage();

    fireEvent.click(screen.getByRole('button', { name: 'Agregar producto online' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cobrar venta' }));

    await vi.waitFor(() => {
      expect(mocks.createSaleMutateAsync).toHaveBeenCalledTimes(1);
    });
  });

  // ── PR-OFF-07: snapshot expiry + pending-limit guardrails ──────────────────

  it('offline: shows the expiry block message and disables saving when expired', () => {
    mocks.isOffline = true;
    // generated_at far in the past → expired regardless of the wall clock.
    mocks.snapshot = makeSnapshot({ generated_at: '2020-01-01T00:00:00.000Z' });
    renderPage();

    const notice = screen.getByTestId('offline-contingency-notice');
    expect(notice).toBeInTheDocument();
    expect(screen.getByTestId('offline-contingency-block').textContent).toContain(
      'Los datos offline están vencidos',
    );
    expect(
      screen.getByRole('button', { name: 'Guardar venta offline' }),
    ).toBeDisabled();
  });

  it('offline: blocks adding products to the cart when the snapshot expired', () => {
    mocks.isOffline = true;
    mocks.snapshot = makeSnapshot({ generated_at: '2020-01-01T00:00:00.000Z' });
    renderPage();

    fireEvent.click(
      screen.getByRole('button', { name: /Agregar Cerveza al carrito/i }),
    );

    expect(screen.getByTestId('cart-state').textContent).toBe('carrito-vacio');
  });

  it('offline: shows the expiring-soon warning inside the warning window', () => {
    mocks.isOffline = true;
    // generated ~23h ago, expires in 24h → ~1h left (inside the 2h window).
    mocks.snapshot = makeSnapshot({
      generated_at: new Date(Date.now() - 23 * 60 * 60 * 1000).toISOString(),
    });
    renderPage();

    expect(screen.getByTestId('offline-contingency-warning').textContent).toContain(
      'Los datos offline están por vencer',
    );
    // Still operable — the warning does not block saving.
    expect(
      screen.getByRole('button', { name: /Agregar Cerveza al carrito/i }),
    ).toBeInTheDocument();
  });

  // ── PR-OFF-08: copy + kitchen-order offline blocking ───────────────────────

  it('offline: shows the updated quick-sale sync copy, not the stale "no se pueden finalizar" text', () => {
    mocks.isOffline = true;
    mocks.snapshot = makeSnapshot();
    renderPage();

    expect(
      screen.getByText(/se guardarán localmente y se sincronizarán cuando vuelva la conexión/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/todavía no se pueden finalizar sin conexión/i),
    ).not.toBeInTheDocument();
  });

  it('offline: hides "Pedido con cocina" even when kitchen orders are enabled', () => {
    mocks.isOffline = true;
    mocks.snapshot = makeSnapshot();
    mocks.operationSettings.kitchen_enabled = true;
    mocks.operationSettings.counter_orders_enabled = true;
    renderPage();

    expect(
      screen.queryByRole('button', { name: 'Pedido con cocina' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/Pedido con cocina no está disponible sin conexión/i),
    ).toBeInTheDocument();
    // Only the offline quick-sale flow remains.
    expect(
      screen.getByRole('button', { name: 'Guardar venta offline' }),
    ).toBeInTheDocument();
  });

  it('offline: forces quick sale even when default_pos_mode is kitchen_order', () => {
    mocks.isOffline = true;
    mocks.snapshot = makeSnapshot();
    mocks.operationSettings.kitchen_enabled = true;
    mocks.operationSettings.counter_orders_enabled = true;
    mocks.operationSettings.default_pos_mode = 'kitchen_order';
    renderPage();

    expect(
      screen.queryByRole('button', { name: 'Pedido con cocina' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Guardar venta offline' }),
    ).toBeInTheDocument();
  });

  it('offline with kitchen enabled: saving creates a quick-sale pending item, never a counter order', async () => {
    mocks.isOffline = true;
    mocks.snapshot = makeSnapshot();
    mocks.operationSettings.kitchen_enabled = true;
    mocks.operationSettings.counter_orders_enabled = true;
    renderPage();

    fireEvent.click(
      screen.getByRole('button', { name: /Agregar Cerveza al carrito/i }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Guardar venta offline' }));

    await vi.waitFor(async () => {
      expect(await listOfflineSales(salesStore)).toHaveLength(1);
    });

    const [sale] = await listOfflineSales(salesStore);
    expect(sale.source).toBe('pos_offline');
    expect(sale.status).toBe('pending');
    // The kitchen/counter-order path must never run offline.
    expect(mocks.createCounterOrderMutateAsync).not.toHaveBeenCalled();
    expect(mocks.createSaleMutateAsync).not.toHaveBeenCalled();
  });
});


