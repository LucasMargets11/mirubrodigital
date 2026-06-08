import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { KitchenTicket } from '@/app/app/kitchen/components/kitchen-ticket';
import type { KitchenOrder } from '@/features/orders/types';

const baseOrder = (itemStatuses: Array<'pending' | 'in_progress' | 'ready' | 'done'>): KitchenOrder => ({
  id: 'order-1',
  number: 101,
  status: 'sent',
  status_label: 'Enviada',
  channel: 'dine_in',
  channel_label: 'Salón',
  channel_display: 'Salón',
  table_id: 'table-1',
  table_code: 'M1',
  table_name: 'Mesa 1',
  customer_name: '',
  note: '',
  total_amount: '1000.00',
  subtotal_amount: '1000.00',
  opened_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  closed_at: null,
  is_paid: false,
  is_editable: true,
  sale_id: null,
  sale_number: null,
  sale_total: null,
  elapsed_seconds: 120,
  items: itemStatuses.map((status, index) => ({
    id: `item-${index + 1}`,
    name: `Item ${index + 1}`,
    note: '',
    quantity: '1.00',
    unit_price: '1000.00',
    total_price: '1000.00',
    product_id: null,
    modifiers: [],
    sold_without_stock: false,
    kitchen_status: status,
    kitchen_started_at: null,
    kitchen_ready_at: null,
    kitchen_done_at: null,
  })),
});

describe('KitchenTicket flow', () => {
  it('pending order shows "Marcar en preparación" and not "Marcar todo listo"', () => {
    render(
      <KitchenTicket
        order={baseOrder(['pending'])}
        onUpdateItem={vi.fn()}
        onUpdateOrder={vi.fn()}
      />
    );

    expect(screen.getByRole('button', { name: 'Marcar en preparación' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Marcar todo listo' })).not.toBeInTheDocument();
  });

  it('clicking pending bulk action sends in_progress', () => {
    const onUpdateOrder = vi.fn();
    render(
      <KitchenTicket
        order={baseOrder(['pending', 'pending'])}
        onUpdateItem={vi.fn()}
        onUpdateOrder={onUpdateOrder}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Marcar en preparación' }));

    expect(onUpdateOrder).toHaveBeenCalledWith('order-1', 'in_progress');
  });

  it('in_progress order shows "Marcar listo" and sends ready', () => {
    const onUpdateOrder = vi.fn();
    render(
      <KitchenTicket
        order={baseOrder(['in_progress'])}
        onUpdateItem={vi.fn()}
        onUpdateOrder={onUpdateOrder}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Marcar listo' }));

    expect(onUpdateOrder).toHaveBeenCalledWith('order-1', 'ready');
  });

  it('all ready order shows final action "Marcar como retirado" and sends done', () => {
    const onUpdateOrder = vi.fn();
    render(
      <KitchenTicket
        order={baseOrder(['ready', 'ready'])}
        onUpdateItem={vi.fn()}
        onUpdateOrder={onUpdateOrder}
      />
    );

    expect(screen.getByText('Pedido listo')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Marcar como retirado' }));
    expect(onUpdateOrder).toHaveBeenCalledWith('order-1', 'done');
    expect(screen.queryByRole('button', { name: 'Marcar listo' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Marcar todo listo' })).not.toBeInTheDocument();
  });

  it('pending and in_progress orders do not show retiro action', () => {
    const { rerender } = render(
      <KitchenTicket
        order={baseOrder(['pending'])}
        onUpdateItem={vi.fn()}
        onUpdateOrder={vi.fn()}
      />
    );

    expect(screen.queryByRole('button', { name: 'Marcar como retirado' })).not.toBeInTheDocument();

    rerender(
      <KitchenTicket
        order={baseOrder(['in_progress'])}
        onUpdateItem={vi.fn()}
        onUpdateOrder={vi.fn()}
      />
    );

    expect(screen.queryByRole('button', { name: 'Marcar como retirado' })).not.toBeInTheDocument();
  });

  it('elapsed time above 24h is compacted as +24 h', () => {
    const oldOrder = {
      ...baseOrder(['pending']),
      elapsed_seconds: 60 * 2000,
    };

    render(
      <KitchenTicket
        order={oldOrder}
        onUpdateItem={vi.fn()}
        onUpdateOrder={vi.fn()}
      />
    );

    expect(screen.getByText('+24 h')).toBeInTheDocument();
  });

  it('item click transitions pending -> in_progress and in_progress -> ready', () => {
    const onUpdateItem = vi.fn();
    const { rerender } = render(
      <KitchenTicket
        order={baseOrder(['pending'])}
        onUpdateItem={onUpdateItem}
        onUpdateOrder={vi.fn()}
      />
    );

    fireEvent.click(screen.getByText('Item 1'));
    expect(onUpdateItem).toHaveBeenCalledWith('item-1', 'in_progress');

    rerender(
      <KitchenTicket
        order={baseOrder(['in_progress'])}
        onUpdateItem={onUpdateItem}
        onUpdateOrder={vi.fn()}
      />
    );

    fireEvent.click(screen.getByText('Item 1'));
    expect(onUpdateItem).toHaveBeenCalledWith('item-1', 'ready');
  });
});
