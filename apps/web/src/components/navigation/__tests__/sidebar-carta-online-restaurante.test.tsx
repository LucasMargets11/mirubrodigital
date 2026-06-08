import { fireEvent, render, screen } from '@testing-library/react';
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

const CARTA_SUB_ITEMS: Array<{ label: string; href: string }> = [
  { label: 'Mi Carta / QR', href: '/app/carta/publicacion' },
  { label: 'Productos de la carta', href: '/app/carta/productos' },
  { label: 'Configuración', href: '/app/carta/apariencia' },
];

function expandCartaGroup() {
  const parent = screen.getByRole('button', { name: 'Carta Online' });
  fireEvent.click(parent);
  return parent;
}

describe('Sidebar Carta Online for Restaurante Inteligente', () => {
  it('shows Carta Online parent group when restaurante has resto_menu feature', () => {
    mockUseRestaurantOperationSettings.mockReturnValue(operationSettings);

    render(<Sidebar {...baseProps} />);

    expect(screen.getByRole('button', { name: 'Carta Online' })).toBeInTheDocument();
  });

  it('shows the three sub-items with correct routes when expanded', () => {
    mockUseRestaurantOperationSettings.mockReturnValue(operationSettings);

    render(<Sidebar {...baseProps} />);
    expandCartaGroup();

    for (const { label, href } of CARTA_SUB_ITEMS) {
      const link = screen.getByRole('link', { name: label });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute('href', href);
    }
  });

  it('does NOT show a Carteles sub-item inside Carta Online', () => {
    mockUseRestaurantOperationSettings.mockReturnValue(operationSettings);

    render(<Sidebar {...baseProps} />);
    expandCartaGroup();

    // The only "Carteles" links belong to other modules (QR de Reseñas / Gestión),
    // never inside the expanded Carta Online group.
    const cartaGroup = screen.getByRole('button', { name: 'Carta Online' }).parentElement;
    expect(cartaGroup?.textContent).not.toContain('Carteles');
  });

  it('keeps Carta Online and its sub-items visible when tables are disabled', () => {
    mockUseRestaurantOperationSettings.mockReturnValue({
      data: { ...operationSettings.data, tables_enabled: false },
    });

    render(<Sidebar {...baseProps} />);
    expandCartaGroup();

    expect(screen.getByRole('link', { name: 'Mi Carta / QR' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Productos de la carta' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Mapa de mesas' })).not.toBeInTheDocument();
  });

  it('keeps Carta Online and its sub-items visible when kitchen is disabled', () => {
    mockUseRestaurantOperationSettings.mockReturnValue({
      data: { ...operationSettings.data, kitchen_enabled: false },
    });

    render(<Sidebar {...baseProps} />);
    expandCartaGroup();

    expect(screen.getByRole('link', { name: 'Mi Carta / QR' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Configuración' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Cocina en vivo' })).not.toBeInTheDocument();
  });

  it('hides Carta Online when resto_menu feature is disabled', () => {
    mockUseRestaurantOperationSettings.mockReturnValue(operationSettings);

    render(
      <Sidebar
        {...baseProps}
        features={{ ...baseProps.features, resto_menu: false }}
      />,
    );

    expect(screen.queryByRole('button', { name: 'Carta Online' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Mi Carta / QR' })).not.toBeInTheDocument();
  });

  it('hides Carta Online when user lacks view_menu permission', () => {
    mockUseRestaurantOperationSettings.mockReturnValue(operationSettings);

    render(
      <Sidebar
        {...baseProps}
        permissions={{ ...baseProps.permissions, view_menu: false }}
      />,
    );

    expect(screen.queryByRole('button', { name: 'Carta Online' })).not.toBeInTheDocument();
  });
});
