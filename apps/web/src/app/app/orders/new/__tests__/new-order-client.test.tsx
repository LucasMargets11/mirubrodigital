import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { RestaurantOperationSettings } from '@/features/resto/types';
import type { MenuProductSelection } from '@/components/orders/menu-picker';
import type { RestaurantTableNode } from '@/features/tables/types';

import { NewOrderClient } from '../new-order-client';

const mocks = vi.hoisted(() => ({
  settings: {
    tables_enabled: true,
    kitchen_enabled: true,
    counter_orders_enabled: true,
    pos_quick_sale_enabled: true,
    allow_pickup_orders: true,
    allow_dine_in_orders: true,
    allow_delivery_orders: false,
    default_pos_mode: 'kitchen_order' as const,
  } as RestaurantOperationSettings,
  tables: [] as RestaurantTableNode[],
  startOrder: vi.fn(),
  createOrderItem: vi.fn(),
  createOrderWithItems: vi.fn(),
  cancelOrder: vi.fn(),
  routerReplace: vi.fn(),
  routerPush: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/app/orders/new',
  useRouter: () => ({
    replace: mocks.routerReplace,
    push: mocks.routerPush,
  }),
}));

vi.mock('@/features/resto/hooks', async () => {
  const actual = await vi.importActual<typeof import('@/features/resto/hooks')>(
    '@/features/resto/hooks',
  );
  return {
    ...actual,
    useRestaurantOperationSettings: () => ({
      data: mocks.settings,
      isLoading: false,
      isError: false,
    }),
  };
});

vi.mock('@/features/tables/hooks', () => ({
  tablesKeys: { mapState: () => ['tables', 'map-state'] },
  useRestaurantTablesMapState: () => ({
    data: { tables: mocks.tables, layout: undefined },
    isLoading: false,
    isError: false,
  }),
}));

vi.mock('@/features/gestion/hooks', () => ({
  useCommercialSettingsQuery: () => ({ data: undefined, isLoading: false }),
}));

vi.mock('@/features/orders/api', () => ({
  startOrder: (...args: unknown[]) => mocks.startOrder(...args),
  createOrderItem: (...args: unknown[]) => mocks.createOrderItem(...args),
  createOrderWithItems: (...args: unknown[]) => mocks.createOrderWithItems(...args),
  cancelOrder: (...args: unknown[]) => mocks.cancelOrder(...args),
}));

vi.mock('@/components/orders/menu-picker', () => ({
  MenuPicker: ({ onProductSelect }: { onProductSelect: (p: MenuProductSelection) => void }) => (
    <button
      type="button"
      data-testid="add-product"
      onClick={() =>
        onProductSelect({
          id: 'prod-1',
          name: 'Café',
          price: 1200,
          sku: null,
          categoryId: null,
          categoryName: null,
          description: '',
          stockStatus: 'in' as MenuProductSelection['stockStatus'],
          isAvailable: true,
        })
      }
    >
      Agregar producto
    </button>
  ),
}));

vi.mock('@/components/orders/table-map-embed', () => ({
  TableMapEmbed: ({
    onSelectTable,
  }: {
    onSelectTable?: (id: string, snapshot?: RestaurantTableNode) => void;
  }) => (
    <button
      type="button"
      data-testid="select-table"
      onClick={() =>
        onSelectTable?.('table-1', { id: 'table-1', state: 'FREE' } as RestaurantTableNode)
      }
    >
      Mesa 1
    </button>
  ),
}));

function renderClient() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <NewOrderClient />
    </QueryClientProvider>,
  );
}

function setSettings(overrides: Partial<RestaurantOperationSettings>) {
  mocks.settings = { ...mocks.settings, ...overrides };
}

const submitButton = () => screen.getByRole('button', { name: /Confirmar orden|Creando orden/ });

describe('NewOrderClient channels', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.tables = [];
    mocks.settings = {
      tables_enabled: true,
      kitchen_enabled: true,
      counter_orders_enabled: true,
      pos_quick_sale_enabled: true,
      allow_pickup_orders: true,
      allow_dine_in_orders: true,
      allow_delivery_orders: false,
      default_pos_mode: 'kitchen_order',
    };
  });

  it('enables order creation via pickup when tables are disabled but pickup is allowed', async () => {
    setSettings({
      tables_enabled: false,
      allow_dine_in_orders: false,
      allow_pickup_orders: true,
    });
    mocks.createOrderWithItems.mockResolvedValue({ id: 'order-1' });

    renderClient();

    expect(screen.queryByTestId('channel-option-dine_in')).not.toBeInTheDocument();
    expect(screen.getByTestId('channel-option-pickup')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('add-product'));
    expect(submitButton()).not.toBeDisabled();

    fireEvent.click(submitButton());

    await waitFor(() => {
      expect(mocks.createOrderWithItems).toHaveBeenCalledTimes(1);
    });
    expect(mocks.createOrderWithItems).toHaveBeenCalledWith(
      expect.objectContaining({ channel: 'pickup' }),
    );
    expect(mocks.startOrder).not.toHaveBeenCalled();
  });

  it('creates a delivery order without a table', async () => {
    setSettings({
      tables_enabled: false,
      allow_dine_in_orders: false,
      allow_pickup_orders: false,
      allow_delivery_orders: true,
    });
    mocks.createOrderWithItems.mockResolvedValue({ id: 'order-2' });

    renderClient();

    expect(screen.getByTestId('channel-option-delivery')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('add-product'));
    fireEvent.click(submitButton());

    await waitFor(() => {
      expect(mocks.createOrderWithItems).toHaveBeenCalledWith(
        expect.objectContaining({ channel: 'delivery' }),
      );
    });
  });

  it('blocks creation and shows a message when all channels are disabled', () => {
    setSettings({
      tables_enabled: false,
      allow_dine_in_orders: false,
      allow_pickup_orders: false,
      allow_delivery_orders: false,
    });

    renderClient();

    expect(screen.getByTestId('no-channels-message')).toHaveTextContent(
      'No hay canales de pedido habilitados. Activá retiro, salón o delivery desde Configuración Operativa.',
    );
    fireEvent.click(screen.getByTestId('add-product'));
    expect(submitButton()).toBeDisabled();
  });

  it('keeps the dine-in flow working when tables and salón orders are enabled', async () => {
    setSettings({ tables_enabled: true, allow_dine_in_orders: true });
    mocks.startOrder.mockResolvedValue({ id: 'order-3' });
    mocks.createOrderItem.mockResolvedValue({ id: 'order-3' });

    renderClient();

    expect(screen.getByTestId('channel-option-dine_in')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('add-product'));
    // Without a table selected the dine-in submit stays disabled.
    expect(submitButton()).toBeDisabled();

    fireEvent.click(screen.getByTestId('select-table'));
    expect(submitButton()).not.toBeDisabled();

    fireEvent.click(submitButton());

    await waitFor(() => {
      expect(mocks.startOrder).toHaveBeenCalledTimes(1);
    });
    expect(mocks.startOrder).toHaveBeenCalledWith(
      expect.objectContaining({ channel: 'dine_in', table_id: 'table-1' }),
    );
    expect(mocks.createOrderWithItems).not.toHaveBeenCalled();
  });
});
