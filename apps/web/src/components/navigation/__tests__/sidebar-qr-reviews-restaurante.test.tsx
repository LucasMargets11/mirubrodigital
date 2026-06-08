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

const SUB_ITEMS: Array<{ label: string; href: string }> = [
  { label: 'Mi QR', href: '/app/resenas/qr' },
  { label: 'Feedback', href: '/app/resenas/feedback' },
  { label: 'Configuración', href: '/app/resenas/configuracion' },
  { label: 'Carteles', href: '/app/resenas/carteles' },
];

function expandReviewsGroup() {
  const parent = screen.getByRole('button', { name: 'QR de Reseñas' });
  fireEvent.click(parent);
  return parent;
}

describe('Sidebar QR de Reseñas visibility for Restaurante Inteligente', () => {
  it('shows QR de Reseñas parent group when restaurante has qr_reviews_core feature', () => {
    mockUseRestaurantOperationSettings.mockReturnValue(operationSettings);

    render(<Sidebar {...baseProps} />);

    expect(screen.getByRole('button', { name: 'QR de Reseñas' })).toBeInTheDocument();
  });

  it('shows all four sub-items with correct routes when expanded', () => {
    mockUseRestaurantOperationSettings.mockReturnValue(operationSettings);

    render(<Sidebar {...baseProps} />);
    expandReviewsGroup();

    for (const { label, href } of SUB_ITEMS) {
      const link = screen.getByRole('link', { name: label });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute('href', href);
    }
  });

  it('hides QR de Reseñas when qr_reviews_core feature is disabled', () => {
    mockUseRestaurantOperationSettings.mockReturnValue(operationSettings);

    render(
      <Sidebar
        {...baseProps}
        features={{ ...baseProps.features, qr_reviews_core: false }}
      />,
    );

    expect(screen.queryByRole('button', { name: 'QR de Reseñas' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Mi QR' })).not.toBeInTheDocument();
  });

  it('hides QR de Reseñas when user lacks manage_reviews permission', () => {
    mockUseRestaurantOperationSettings.mockReturnValue(operationSettings);

    render(
      <Sidebar
        {...baseProps}
        permissions={{ ...baseProps.permissions, manage_reviews: false }}
      />,
    );

    expect(screen.queryByRole('button', { name: 'QR de Reseñas' })).not.toBeInTheDocument();
  });

  it('keeps QR de Reseñas and its sub-items visible when tables are disabled', () => {
    mockUseRestaurantOperationSettings.mockReturnValue({
      data: { ...operationSettings.data, tables_enabled: false },
    });

    render(<Sidebar {...baseProps} />);
    expandReviewsGroup();

    expect(screen.getByRole('link', { name: 'Mi QR' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Carteles' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Mapa de mesas' })).not.toBeInTheDocument();
  });

  it('keeps QR de Reseñas and its sub-items visible when kitchen is disabled', () => {
    mockUseRestaurantOperationSettings.mockReturnValue({
      data: { ...operationSettings.data, kitchen_enabled: false },
    });

    render(<Sidebar {...baseProps} />);
    expandReviewsGroup();

    expect(screen.getByRole('link', { name: 'Feedback' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Configuración' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Cocina en vivo' })).not.toBeInTheDocument();
  });
});
