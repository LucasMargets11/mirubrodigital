import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { AnchorHTMLAttributes } from 'react';

const mockUseRestaurantOperationSettings = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/app/dashboard',
}));

vi.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock('@/features/resto/hooks', () => ({
  useRestaurantOperationSettings: () => mockUseRestaurantOperationSettings(),
  getEffectiveRestaurantOperationSettings: (value: unknown) => value,
}));

vi.mock('@/lib/auth/client', () => ({
  logout: vi.fn(),
}));

import { Sidebar } from '@/components/navigation/sidebar';

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

Object.defineProperty(globalThis, 'ResizeObserver', {
  writable: true,
  value: ResizeObserverMock,
});

const baseProps = {
  businessName: 'Resto Demo',
  service: 'restaurante',
  features: {
    resto_tables: true,
    resto_orders: true,
    resto_kitchen: true,
    resto_menu: true,
    products: true,
    inventory: true,
    sales: true,
    invoices: true,
    cash: true,
    settings: true,
    resto_reports: true,
    multi_branch: true,
  },
  permissions: {
    view_tables: true,
    manage_order_table: true,
    view_orders: true,
    view_kitchen_board: true,
    view_menu: true,
    manage_tables: true,
    manage_settings: true,
    view_cash: true,
    view_restaurant_reports: true,
  },
  userName: 'Owner Demo',
  role: 'owner',
  subscriptionStatus: 'active',
  subscriptionPlan: 'plus',
} satisfies Parameters<typeof Sidebar>[0];

describe('Sidebar operation settings visibility', () => {
  it('hides kitchen link when kitchen is disabled', () => {
    mockUseRestaurantOperationSettings.mockReturnValue({
      data: {
        tables_enabled: true,
        kitchen_enabled: false,
        counter_orders_enabled: true,
        pos_quick_sale_enabled: true,
        allow_pickup_orders: true,
        allow_dine_in_orders: true,
        allow_delivery_orders: false,
        default_pos_mode: 'quick_sale',
      },
    });

    render(<Sidebar {...baseProps} />);

    expect(screen.queryByRole('link', { name: 'Cocina en vivo' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Mapa de mesas' })).toBeInTheDocument();
  });

  it('hides tables links when tables are disabled', () => {
    mockUseRestaurantOperationSettings.mockReturnValue({
      data: {
        tables_enabled: false,
        kitchen_enabled: true,
        counter_orders_enabled: true,
        pos_quick_sale_enabled: true,
        allow_pickup_orders: true,
        allow_dine_in_orders: true,
        allow_delivery_orders: false,
        default_pos_mode: 'quick_sale',
      },
    });

    render(<Sidebar {...baseProps} />);

    expect(screen.queryByRole('link', { name: 'Mapa de mesas' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Configurar mesas' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Cocina en vivo' })).toBeInTheDocument();
  });
});
