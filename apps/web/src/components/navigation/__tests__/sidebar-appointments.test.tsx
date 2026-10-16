import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { AnchorHTMLAttributes } from 'react';

vi.mock('next/navigation', () => ({
  usePathname: () => '/app/turnos',
}));

vi.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock('@/features/resto/hooks', () => ({
  useRestaurantOperationSettings: () => ({ data: undefined }),
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
  businessName: 'Turnos Demo',
  service: 'appointments',
  features: {
    appointments_core: true,
    dashboard: true,
    services: true,
    settings: true,
  },
  permissions: {
    manage_users: true,
  },
  userName: 'Owner Demo',
  role: 'owner',
  subscriptionStatus: 'active',
  subscriptionPlan: 'appointments_base',
} satisfies Parameters<typeof Sidebar>[0];

describe('Sidebar Turnos navigation', () => {
  it('shows the Turnos group with an Inicio link pointing to /app/turnos', () => {
    render(<Sidebar {...baseProps} />);

    expect(screen.getAllByText('Turnos').length).toBeGreaterThan(0);
    const link = screen.getByRole('link', { name: 'Inicio' });
    expect(link).toHaveAttribute('href', '/app/turnos');
  });

  it('shows a Turnos link pointing to /app/turnos/turnos', () => {
    render(<Sidebar {...baseProps} permissions={{ ...baseProps.permissions, view_appointments: true }} />);

    const link = screen.getByRole('link', { name: 'Turnos' });
    expect(link).toHaveAttribute('href', '/app/turnos/turnos');
  });

  it('shows Clientes (shared customer core) pointing to /app/clientes', () => {
    render(
      <Sidebar
        {...baseProps}
        features={{ ...baseProps.features, customers: true }}
        permissions={{ ...baseProps.permissions, view_appointments: true, view_customers: true }}
      />,
    );

    const link = screen.getByRole('link', { name: 'Clientes' });
    expect(link).toHaveAttribute('href', '/app/clientes');
  });

  it('hides Clientes without view_customers permission', () => {
    render(<Sidebar {...baseProps} features={{ ...baseProps.features, customers: true }} />);

    expect(screen.queryByRole('link', { name: 'Clientes' })).not.toBeInTheDocument();
  });

  it('does not render commercial Gestión items next to Clientes', () => {
    render(
      <Sidebar
        {...baseProps}
        features={{ ...baseProps.features, customers: true }}
        permissions={{ ...baseProps.permissions, view_customers: true }}
      />,
    );

    for (const name of ['Ventas', 'Presupuestos', 'Caja', 'Stock']) {
      expect(screen.queryByRole('link', { name })).not.toBeInTheDocument();
    }
  });

  // LEADS 05A: flag `leads` (entitlement appointments.leads) + permiso view_leads.
  it('shows Leads pointing to /app/turnos/leads with the leads flag and view_leads', () => {
    render(
      <Sidebar
        {...baseProps}
        features={{ ...baseProps.features, leads: true }}
        permissions={{ ...baseProps.permissions, view_leads: true }}
      />,
    );

    expect(screen.getByRole('link', { name: 'Leads' })).toHaveAttribute('href', '/app/turnos/leads');
  });

  it('hides Leads without view_leads permission', () => {
    render(<Sidebar {...baseProps} features={{ ...baseProps.features, leads: true }} />);

    expect(screen.queryByRole('link', { name: 'Leads' })).not.toBeInTheDocument();
  });

  it('hides Leads when the plan does not include the leads entitlement', () => {
    render(
      <Sidebar
        {...baseProps}
        features={{ ...baseProps.features, leads: false }}
        permissions={{ ...baseProps.permissions, view_leads: true }}
      />,
    );

    expect(screen.queryByRole('link', { name: 'Leads' })).not.toBeInTheDocument();
  });

  it('does not render nav items from other products (gestion/qr_reviews)', () => {
    render(<Sidebar {...baseProps} />);

    expect(screen.queryByRole('link', { name: 'Productos' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Mi QR' })).not.toBeInTheDocument();
    expect(screen.queryByText('Gestión Comercial')).not.toBeInTheDocument();
  });
});
