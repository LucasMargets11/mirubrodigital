import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children, ...props }: any) => (
    <a href={typeof href === 'string' ? href : href?.pathname} {...props}>{children}</a>
  ),
}));

import { ClientesContent } from '../clientes-content';
import type { AdminClientList } from '@/lib/admin/types';

const CLIENT_LIST: AdminClientList = {
  results: [
    {
      id: 7,
      name: 'Negocio Demo',
      slug: 'negocio-demo',
      email: 'owner@demo.com',
      status: 'active',
      plan: 'gestion_pro',
      subscription_status: 'active',
      created_at: '2026-01-01T00:00:00Z',
      next_renewal: null,
      user_count: 3,
      branch_count: 0,
      risk_badges: [],
      service_type: 'gestion',
    },
  ],
  total: 1,
  page: 1,
  page_size: 25,
  total_pages: 1,
};

describe('ClientesContent — ADMIN-CLIENTES 03C access to "Nuevo cliente"', () => {
  it('shows the "Nuevo cliente" button for superadmin, pointing at /admin/clientes/nuevo', () => {
    render(
      <ClientesContent initialData={CLIENT_LIST} kpis={null} initialParams={{}} canCreateClient={true} />,
    );
    const link = screen.getByRole('link', { name: /nuevo cliente/i });
    expect(link).toHaveAttribute('href', '/admin/clientes/nuevo');
  });

  it('hides the "Nuevo cliente" button for operations (or any non-superadmin)', () => {
    render(
      <ClientesContent initialData={CLIENT_LIST} kpis={null} initialParams={{}} canCreateClient={false} />,
    );
    expect(screen.queryByRole('link', { name: /nuevo cliente/i })).not.toBeInTheDocument();
  });

  it('still renders the existing search, table and pagination (no regression)', () => {
    render(
      <ClientesContent initialData={CLIENT_LIST} kpis={null} initialParams={{}} canCreateClient={false} />,
    );
    expect(screen.getByRole('button', { name: /^buscar$/i })).toBeInTheDocument();
    expect(screen.getByText('Negocio Demo')).toBeInTheDocument();
    expect(screen.getByText(/1 cliente en total/i)).toBeInTheDocument();
  });
});
