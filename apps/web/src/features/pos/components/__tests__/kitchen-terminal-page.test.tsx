import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { KitchenTerminalPage } from '../KitchenTerminalPage';

const mocks = vi.hoisted(() => ({
  useEmployeeSession: vi.fn(),
  useRestaurantOperationSettings: vi.fn(),
  getEffectiveRestaurantOperationSettings: vi.fn(),
  posFetchKitchenBoard: vi.fn(),
  posUpdateKitchenItemStatus: vi.fn(),
  posUpdateKitchenOrderBulk: vi.fn(),
}));

vi.mock('../../context', () => ({
  useEmployeeSession: mocks.useEmployeeSession,
}));

vi.mock('@/features/resto/hooks', () => ({
  useRestaurantOperationSettings: mocks.useRestaurantOperationSettings,
  getEffectiveRestaurantOperationSettings: mocks.getEffectiveRestaurantOperationSettings,
}));

vi.mock('@/lib/api/pos', () => ({
  posFetchKitchenBoard: mocks.posFetchKitchenBoard,
  posUpdateKitchenItemStatus: mocks.posUpdateKitchenItemStatus,
  posUpdateKitchenOrderBulk: mocks.posUpdateKitchenOrderBulk,
}));

function createOrder(status: 'pending' | 'in_progress' | 'ready') {
  return {
    id: `order-${status}`,
    number: 101,
    status: 'sent',
    status_label: 'Enviado',
    channel: 'pickup',
    channel_label: 'Retiro',
    channel_display: 'Retiro',
    table_id: null,
    table_code: null,
    table_name: '',
    customer_name: 'Cliente POS',
    note: 'Sin cebolla',
    total_amount: '0',
    subtotal_amount: '0',
    opened_at: '2026-06-05T00:00:00Z',
    updated_at: '2026-06-05T00:00:00Z',
    closed_at: null,
    is_paid: false,
    is_editable: true,
    sale_id: null,
    sale_number: null,
    sale_total: null,
    elapsed_seconds: 120,
    items: [
      {
        id: `item-${status}`,
        name: 'Hamburguesa',
        note: 'sin sal',
        quantity: '1',
        unit_price: '0',
        total_price: '0',
        product_id: null,
        modifiers: [],
        sold_without_stock: false,
        kitchen_status: status,
        kitchen_started_at: null,
        kitchen_ready_at: null,
        kitchen_done_at: null,
      },
    ],
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <KitchenTerminalPage />
    </QueryClientProvider>,
  );
}

describe('KitchenTerminalPage', () => {
  beforeEach(() => {
    mocks.useEmployeeSession.mockReturnValue({
      session: {
        status: 'authenticated',
        token: 'tok-kitchen',
        employee: {
          id: 'emp-1',
          employee_code: 'EMP-001',
          display_name: 'Cocina Demo',
          full_name: 'Cocina Demo',
          role_type: 'kitchen',
          branch: 1,
          branch_name: 'Centro',
          status: 'active',
          must_change_pin: false,
          business_id: 1,
          business_name: 'Demo Fast Food',
        },
        mustChangePin: false,
      },
      logout: vi.fn(),
    });

    mocks.useRestaurantOperationSettings.mockReturnValue({ data: { kitchen_enabled: true } });
    mocks.getEffectiveRestaurantOperationSettings.mockReturnValue({ kitchen_enabled: true });

    mocks.posFetchKitchenBoard.mockResolvedValue([]);
    mocks.posUpdateKitchenItemStatus.mockResolvedValue({});
    mocks.posUpdateKitchenOrderBulk.mockResolvedValue({});
  });

  it('muestra estado vacío sin pedidos', async () => {
    renderPage();

    expect(await screen.findByText('No hay pedidos pendientes en cocina.')).toBeInTheDocument();
  });

  it('muestra pedidos pendientes', async () => {
    mocks.posFetchKitchenBoard.mockResolvedValue([createOrder('pending')]);

    renderPage();

    expect(await screen.findByText('Marcar en preparación')).toBeInTheDocument();
    expect(screen.getByText('Hamburguesa')).toBeInTheDocument();
  });

  it('pedido pending muestra Marcar en preparación y llama endpoint in_progress', async () => {
    mocks.posFetchKitchenBoard.mockResolvedValue([createOrder('pending')]);

    renderPage();

    const button = await screen.findByRole('button', { name: 'Marcar en preparación' });
    fireEvent.click(button);

    await waitFor(() => {
      expect(mocks.posUpdateKitchenOrderBulk).toHaveBeenCalledWith('tok-kitchen', 'order-pending', 'in_progress');
    });
  });

  it('pedido in_progress muestra Marcar listo y llama endpoint ready', async () => {
    mocks.posFetchKitchenBoard.mockResolvedValue([createOrder('in_progress')]);

    renderPage();

    const button = await screen.findByRole('button', { name: 'Marcar listo' });
    fireEvent.click(button);

    await waitFor(() => {
      expect(mocks.posUpdateKitchenOrderBulk).toHaveBeenCalledWith('tok-kitchen', 'order-in_progress', 'ready');
    });
  });

  it('pedido ready muestra Pedido listo y botón de retirado', async () => {
    mocks.posFetchKitchenBoard.mockResolvedValue([createOrder('ready')]);

    renderPage();

    expect(await screen.findByText('Pedido listo')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Marcar como retirado' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Marcar todo listo' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Marcar listo' })).not.toBeInTheDocument();
  });

  it('click en retirado llama endpoint con done', async () => {
    mocks.posFetchKitchenBoard.mockResolvedValue([createOrder('ready')]);

    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Marcar como retirado' }));

    await waitFor(() => {
      expect(mocks.posUpdateKitchenOrderBulk).toHaveBeenCalledWith('tok-kitchen', 'order-ready', 'done');
    });
  });

  it('pedido done deja de renderizarse en tablero activo luego de retirar', async () => {
    mocks.posFetchKitchenBoard
      .mockResolvedValueOnce([createOrder('ready')])
      .mockResolvedValueOnce([]);

    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Marcar como retirado' }));

    await waitFor(() => {
      expect(screen.getByText('No hay pedidos pendientes en cocina.')).toBeInTheDocument();
    });
  });

  it('cocina desactivada muestra mensaje correcto', async () => {
    mocks.useRestaurantOperationSettings.mockReturnValue({ data: { kitchen_enabled: false } });
    mocks.getEffectiveRestaurantOperationSettings.mockReturnValue({ kitchen_enabled: false });

    renderPage();

    expect(await screen.findByText('Cocina desactivada para este negocio.')).toBeInTheDocument();
  });

  it('empleado cocina puede ver pantalla de cocina', async () => {
    renderPage();

    expect(await screen.findByText('Cocina en Vivo')).toBeInTheDocument();
    expect(screen.getByText('Cocina Demo · Cocina')).toBeInTheDocument();
  });
});
