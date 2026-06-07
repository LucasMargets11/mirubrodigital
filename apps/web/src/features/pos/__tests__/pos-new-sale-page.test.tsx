import React from 'react';
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PosProduct } from '@/types/pos-cash';
import { PosNewSalePage } from '../components/PosNewSalePage';

const mocks = vi.hoisted(() => ({
  routerPush: vi.fn(),
  routerReplace: vi.fn(),
  createSaleMutateAsync: vi.fn(),
  createCounterOrderMutateAsync: vi.fn(),
  handleError: vi.fn((err: unknown) => (err instanceof Error ? err.message : 'Error inesperado.')),
  useRestaurantOperationSettings: vi.fn(),
  offlineCatalog: {
    isOffline: false,
    status: 'online' as string,
    snapshot: null as unknown,
    savedAt: null as string | null,
    products: [] as unknown[],
    categories: [] as unknown[],
    paymentMethods: [] as unknown[],
    canBuildCart: false,
  },
  operationSettings: {
    tables_enabled: true,
    kitchen_enabled: true,
    counter_orders_enabled: true,
    pos_quick_sale_enabled: true,
    allow_pickup_orders: true,
    allow_dine_in_orders: true,
    allow_delivery_orders: false,
    default_pos_mode: 'quick_sale' as 'quick_sale' | 'kitchen_order',
  },
}));

const productFixture: PosProduct = {
  id: 'prod-1',
  name: 'Hamburguesa clásica',
  sku: 'HB-1',
  price: '2500.00',
  stock_quantity: '10.00',
  stock_min: '1.00',
  category_id: 'cat-1',
  is_active: true,
};

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.routerPush, replace: mocks.routerReplace }),
}));

vi.mock('../context', () => ({
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

vi.mock('../cash-hooks', () => ({
  usePosCreateSale: () => ({
    mutateAsync: mocks.createSaleMutateAsync,
    isPending: false,
  }),
  usePosCreateCounterOrder: () => ({
    mutateAsync: mocks.createCounterOrderMutateAsync,
    isPending: false,
  }),
  usePosErrorHandler: () => mocks.handleError,
}));

vi.mock('@/features/resto/hooks', () => ({
  useRestaurantOperationSettings: () => {
    mocks.useRestaurantOperationSettings();
    return {
      data: mocks.operationSettings,
      isLoading: false,
      isError: false,
    };
  },
  getEffectiveRestaurantOperationSettings: (value: unknown) => value,
}));

vi.mock('@/features/pos/offline/pos-operation-settings', () => ({
  usePosOperationSettings: () => mocks.operationSettings,
}));

vi.mock('@/features/pos/offline/offline-catalog', () => ({
  usePosOfflineCatalog: () => mocks.offlineCatalog,
}));

vi.mock('@/features/pos/offline/OfflineProductCatalogPanel', () => ({
  OfflineProductCatalogPanel: () => <div data-testid="offline-catalog-panel" />,
}));

vi.mock('@/features/pos/offline/offline-sales-hooks', () => ({
  usePosCaptureOfflineSale: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePosOfflineSalesCount: () => 0,
  OfflineSaleValidationError: class OfflineSaleValidationError extends Error {},
}));

vi.mock('@/features/pos/offline/offline-guard', () => ({
  usePosOfflineGuard: () => ({
    isOffline: false,
    snapshot: null,
    savedAt: null,
    expiry: {
      expiresAt: null,
      isExpired: false,
      isExpiringSoon: false,
      hoursUntilExpiry: null,
    },
    unsyncedCount: 0,
    atPendingLimit: false,
    blockReason: null,
    warningMessage: null,
  }),
}));

vi.mock('@/features/pos/offline/OfflineContingencyNotice', () => ({
  OfflineContingencyNotice: () => <div data-testid="offline-contingency-notice" />,
}));

vi.mock('@/features/pos/offline/offline-sales-panel', () => ({
  OfflineSalesPanel: () => <div data-testid="offline-sales-panel" />,
}));

vi.mock('../components/ProductSearchPanel', () => ({
  ProductSearchPanel: () => <div data-testid="product-search-panel" />,
}));

vi.mock('../components/ProductCatalogPanel', () => ({
  ProductCatalogPanel: ({ onAdd }: { onAdd: (product: PosProduct) => void }) => (
    <button type="button" onClick={() => onAdd(productFixture)}>
      Agregar producto fixture
    </button>
  ),
}));

vi.mock('../components/SaleItemsPanel', () => ({
  SaleItemsPanel: ({ items }: { items: Array<{ product: PosProduct; quantity: number }> }) => (
    <div data-testid="cart-state">
      {items.length === 0 ? 'carrito-vacio' : `items:${items.length}:${items[0]?.product.name}`}
    </div>
  ),
}));

vi.mock('../components/CustomerPanel', () => ({
  CustomerPanel: () => <div data-testid="customer-panel" />,
}));

vi.mock('../components/DiscountPanel', () => ({
  DiscountPanel: () => <div data-testid="discount-panel" />,
}));

vi.mock('../components/SplitPaymentPanel', () => ({
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

vi.mock('../components/SaleSummaryCard', () => ({
  SaleSummaryCard: (props: {
    confirmLabel?: string;
    helperText?: string;
    error: string;
    successMsg: string;
    disabled: boolean;
    isPending: boolean;
    onConfirm: () => void;
  }) => (
    <div>
      <div data-testid="summary-confirm-label">{props.confirmLabel}</div>
      {props.helperText ? <div>{props.helperText}</div> : null}
      {props.error ? <div role="alert">{props.error}</div> : null}
      {props.successMsg ? <div role="status">{props.successMsg}</div> : null}
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

describe('PosNewSalePage kitchen counter mode', () => {
  beforeEach(() => {
    mocks.routerPush.mockReset();
    mocks.createSaleMutateAsync.mockReset();
    mocks.createCounterOrderMutateAsync.mockReset();
    mocks.handleError.mockClear();
    mocks.useRestaurantOperationSettings.mockClear();
    mocks.createSaleMutateAsync.mockResolvedValue({
      sale: {
        id: 'sale-1',
        number: 17,
        status: 'completed',
        status_label: 'Completada',
        payment_method: 'cash',
        payment_method_label: 'Efectivo',
        total: '2500.00',
        subtotal: '2500.00',
        discount: '0.00',
        notes: '',
        cash_session_id: 'cash-1',
        created_at: '2026-06-05T00:00:00Z',
      },
    });
    mocks.createCounterOrderMutateAsync.mockResolvedValue({
      id: 'order-1',
      number: 31,
      status: 'sent',
      status_label: 'Enviado',
      channel: 'pickup',
      channel_label: 'Retiro',
      table_id: null,
      table_code: null,
      table_name: '',
      customer_name: 'Juan',
      note: '',
      total_amount: '2500.00',
      subtotal_amount: '2500.00',
      opened_at: '2026-06-05T00:00:00Z',
      updated_at: '2026-06-05T00:00:00Z',
      closed_at: null,
      is_paid: false,
      is_editable: true,
      items: [],
      sale_id: null,
      sale_number: null,
      sale_total: null,
      invoice: null,
    });
    mocks.operationSettings = {
      tables_enabled: true,
      kitchen_enabled: true,
      counter_orders_enabled: true,
      pos_quick_sale_enabled: true,
      allow_pickup_orders: true,
      allow_dine_in_orders: true,
      allow_delivery_orders: false,
      default_pos_mode: 'quick_sale',
    };
    mocks.offlineCatalog = {
      isOffline: false,
      status: 'online',
      snapshot: null,
      savedAt: null,
      products: [],
      categories: [],
      paymentMethods: [],
      canBuildCart: false,
    };
  });

  it('hides kitchen mode when kitchen_enabled is false', () => {
    mocks.operationSettings.kitchen_enabled = false;
    render(<PosNewSalePage />);

    expect(screen.queryByRole('button', { name: 'Pedido con cocina' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Venta rápida' })).toBeInTheDocument();
  });

  it('hides kitchen mode when counter_orders_enabled is false', () => {
    mocks.operationSettings.counter_orders_enabled = false;
    render(<PosNewSalePage />);

    expect(screen.queryByRole('button', { name: 'Pedido con cocina' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Venta rápida' })).toBeInTheDocument();
  });

  it('shows kitchen mode when kitchen and counter orders are enabled', () => {
    render(<PosNewSalePage />);
    expect(screen.getByRole('button', { name: 'Pedido con cocina' })).toBeInTheDocument();
  });

  it('does not read the owner/admin operation-settings endpoint (PR-OFF-10)', () => {
    render(<PosNewSalePage />);
    // The POS must derive flags from the offline snapshot, never from the
    // owner/admin hook that calls /api/v1/resto/settings/operation/.
    expect(mocks.useRestaurantOperationSettings).not.toHaveBeenCalled();
  });

  it('keeps quick sale as default and calls posCreateSale', async () => {
    render(<PosNewSalePage />);

    expect(screen.getByRole('button', { name: 'Venta rápida' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('summary-confirm-label').textContent).toBe('Cobrar venta');

    fireEvent.click(screen.getByRole('button', { name: 'Agregar producto fixture' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cobrar venta' }));

    await waitFor(() => {
      expect(mocks.createSaleMutateAsync).toHaveBeenCalledTimes(1);
    });
    expect(mocks.createCounterOrderMutateAsync).not.toHaveBeenCalled();
  });

  it('starts in kitchen mode when default_pos_mode is kitchen_order and enabled', () => {
    mocks.operationSettings.default_pos_mode = 'kitchen_order';
    render(<PosNewSalePage />);

    expect(screen.getByRole('button', { name: 'Pedido con cocina' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('summary-confirm-label').textContent).toBe('Enviar a cocina');
  });

  it('falls back to quick sale when default_pos_mode is kitchen_order but kitchen is disabled', () => {
    mocks.operationSettings.default_pos_mode = 'kitchen_order';
    mocks.operationSettings.kitchen_enabled = false;
    render(<PosNewSalePage />);

    expect(screen.getByRole('heading', { name: 'Venta rápida' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Pedido con cocina' })).not.toBeInTheDocument();
    expect(screen.getByTestId('summary-confirm-label').textContent).toBe('Cobrar venta');
  });

  it('in kitchen mode calls createCounterOrder and never posCreateSale', async () => {
    render(<PosNewSalePage />);

    fireEvent.click(screen.getByRole('button', { name: 'Pedido con cocina' }));
    fireEvent.click(screen.getByRole('button', { name: 'Agregar producto fixture' }));
    fireEvent.change(screen.getByLabelText(/Nombre del cliente/i), {
      target: { value: 'Juan' },
    });
    fireEvent.change(screen.getByLabelText(/Nota general/i), {
      target: { value: 'Sin cebolla' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar a cocina' }));

    await waitFor(() => {
      expect(mocks.createCounterOrderMutateAsync).toHaveBeenCalledTimes(1);
    });
    expect(mocks.createSaleMutateAsync).not.toHaveBeenCalled();
    expect(mocks.createCounterOrderMutateAsync).toHaveBeenCalledWith({
      items: [
        {
          product_id: 'prod-1',
          quantity: 1,
          note: undefined,
        },
      ],
      customer_name: 'Juan',
      note: 'Sin cebolla',
      send_to_kitchen: true,
    });
  });

  it('does not allow kitchen submit with an empty cart', () => {
    render(<PosNewSalePage />);

    fireEvent.click(screen.getByRole('button', { name: 'Pedido con cocina' }));

    expect(screen.getByRole('button', { name: 'Enviar a cocina' })).toBeDisabled();
    expect(mocks.createCounterOrderMutateAsync).not.toHaveBeenCalled();
  });

  it('clears the cart after a successful kitchen order', async () => {
    render(<PosNewSalePage />);

    fireEvent.click(screen.getByRole('button', { name: 'Pedido con cocina' }));
    fireEvent.click(screen.getByRole('button', { name: 'Agregar producto fixture' }));

    expect(screen.getByTestId('cart-state').textContent).toContain('items:1');

    fireEvent.click(screen.getByRole('button', { name: 'Enviar a cocina' }));

    await waitFor(() => {
      expect(screen.getByTestId('cart-state').textContent).toBe('carrito-vacio');
    });
    expect(screen.getByText(/Pedido #31 enviado a cocina/i).textContent).toContain('Pedido #31 enviado a cocina');
  });
});

describe('PosNewSalePage back navigation (PR-OFF-11)', () => {
  const originalLocation = window.location;

  beforeEach(() => {
    mocks.routerPush.mockReset();
    mocks.routerReplace.mockReset();
    mocks.offlineCatalog = {
      isOffline: false,
      status: 'online',
      snapshot: null,
      savedAt: null,
      products: [],
      categories: [],
      paymentMethods: [],
      canBuildCart: false,
    };
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: originalLocation,
    });
  });

  it('online: "Volver al terminal" uses router.replace to /pos/terminal', () => {
    render(<PosNewSalePage />);

    fireEvent.click(screen.getByRole('button', { name: 'Volver al terminal' }));

    expect(mocks.routerReplace).toHaveBeenCalledWith('/pos/terminal');
    expect(mocks.routerPush).not.toHaveBeenCalled();
  });

  it('offline: "Volver al terminal" uses router.replace and never hard-navigates', () => {
    const assign = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { ...originalLocation, assign },
    });
    mocks.offlineCatalog = {
      isOffline: true,
      status: 'offline',
      snapshot: null,
      savedAt: '2026-06-07T10:00:00Z',
      products: [],
      categories: [],
      paymentMethods: [],
      canBuildCart: true,
    };

    render(<PosNewSalePage />);

    fireEvent.click(screen.getByRole('button', { name: 'Volver al terminal' }));

    expect(mocks.routerReplace).toHaveBeenCalledWith('/pos/terminal');
    expect(assign).not.toHaveBeenCalled();
    expect(mocks.routerPush).not.toHaveBeenCalled();
  });

  it('offline: "Cancelar" also uses router.replace to /pos/terminal', () => {
    const assign = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { ...originalLocation, assign },
    });
    mocks.offlineCatalog = {
      isOffline: true,
      status: 'offline',
      snapshot: null,
      savedAt: '2026-06-07T10:00:00Z',
      products: [],
      categories: [],
      paymentMethods: [],
      canBuildCart: true,
    };

    render(<PosNewSalePage />);

    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));

    expect(mocks.routerReplace).toHaveBeenCalledWith('/pos/terminal');
    expect(assign).not.toHaveBeenCalled();
    expect(mocks.routerPush).not.toHaveBeenCalled();
  });
});
