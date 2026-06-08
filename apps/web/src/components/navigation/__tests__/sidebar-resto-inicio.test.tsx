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

const operationSettings = {
  data: {
    tables_enabled: true,
    kitchen_enabled: true,
    counter_orders_enabled: true,
    pos_quick_sale_enabled: true,
    allow_pickup_orders: true,
    allow_dine_in_orders: true,
    allow_delivery_orders: false,
    default_pos_mode: 'quick_sale',
  },
};

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
    qr_reviews_core: true,
  },
  permissions: {
    view_tables: true,
    view_orders: true,
    view_kitchen_board: true,
    view_menu: true,
    manage_reviews: true,
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

describe('Sidebar Restaurante Inteligente Inicio', () => {
  it('shows an Inicio link inside Restaurante Inteligente pointing to /app/resto', () => {
    mockUseRestaurantOperationSettings.mockReturnValue(operationSettings);

    render(<Sidebar {...baseProps} />);

    const inicioLinks = screen.getAllByRole('link', { name: 'Inicio' });
    const restoInicio = inicioLinks.find((link) => link.getAttribute('href') === '/app/resto');
    expect(restoInicio).toBeDefined();
  });

  it('keeps the Restaurante Inicio visible when tables are disabled', () => {
    mockUseRestaurantOperationSettings.mockReturnValue({
      data: { ...operationSettings.data, tables_enabled: false },
    });

    render(<Sidebar {...baseProps} />);

    const inicioLinks = screen.getAllByRole('link', { name: 'Inicio' });
    expect(inicioLinks.some((link) => link.getAttribute('href') === '/app/resto')).toBe(true);
    expect(screen.queryByRole('link', { name: 'Mapa de mesas' })).not.toBeInTheDocument();
  });

  it('keeps the Restaurante Inicio visible when kitchen is disabled', () => {
    mockUseRestaurantOperationSettings.mockReturnValue({
      data: { ...operationSettings.data, kitchen_enabled: false },
    });

    render(<Sidebar {...baseProps} />);

    const inicioLinks = screen.getAllByRole('link', { name: 'Inicio' });
    expect(inicioLinks.some((link) => link.getAttribute('href') === '/app/resto')).toBe(true);
    expect(screen.queryByRole('link', { name: 'Cocina en vivo' })).not.toBeInTheDocument();
  });

  it('does not render the Restaurante Inicio for a non-restaurante service', () => {
    mockUseRestaurantOperationSettings.mockReturnValue(operationSettings);

    render(<Sidebar {...baseProps} service="gestion" />);

    const restoInicio = screen
      .queryAllByRole('link', { name: 'Inicio' })
      .find((link) => link.getAttribute('href') === '/app/resto');
    expect(restoInicio).toBeUndefined();
  });
});
