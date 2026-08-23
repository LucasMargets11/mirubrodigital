import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

const redirectMock = vi.fn((path: string) => {
  throw new Error(`REDIRECT:${path}`);
});

vi.mock('next/navigation', () => ({
  redirect: (path: string) => redirectMock(path),
}));

vi.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children, ...props }: any) => (
    <a href={typeof href === 'string' ? href : href?.pathname} {...props}>{children}</a>
  ),
}));

vi.mock('@/lib/admin', () => ({
  getAdminSession: vi.fn(),
}));

vi.mock('../nuevo-cliente-form', () => ({
  NuevoClienteForm: () => <div data-testid="nuevo-cliente-form">form</div>,
}));

import { getAdminSession } from '@/lib/admin';

const getAdminSessionMock = vi.mocked(getAdminSession);

describe('AdminClienteNuevoPage — server-side access gate', () => {
  beforeEach(() => {
    getAdminSessionMock.mockReset();
    redirectMock.mockClear();
  });

  it('renders the form for superadmin', async () => {
    getAdminSessionMock.mockResolvedValue({
      user: { id: 1, email: 'admin@mirubro.com', name: 'Admin' },
      internal_role: 'superadmin',
      authorized_sections: ['clientes'],
    } as any);

    const { default: AdminClienteNuevoPage } = await import('../page');
    const element = await AdminClienteNuevoPage();
    render(element);

    expect(screen.getByTestId('nuevo-cliente-form')).toBeInTheDocument();
    expect(screen.getByText('Nuevo cliente')).toBeInTheDocument();
  });

  it('redirects operations to /admin/clientes without ever rendering the form', async () => {
    getAdminSessionMock.mockResolvedValue({
      user: { id: 2, email: 'ops@mirubro.com', name: 'Ops' },
      internal_role: 'operations',
      authorized_sections: ['clientes'],
    } as any);

    const { default: AdminClienteNuevoPage } = await import('../page');

    await expect(AdminClienteNuevoPage()).rejects.toThrow('REDIRECT:/admin/clientes');
    expect(redirectMock).toHaveBeenCalledWith('/admin/clientes');
  });

  it('redirects support_agent to /admin/clientes', async () => {
    getAdminSessionMock.mockResolvedValue({
      user: { id: 3, email: 'support@mirubro.com', name: 'Support' },
      internal_role: 'support_agent',
      authorized_sections: ['soporte'],
    } as any);

    const { default: AdminClienteNuevoPage } = await import('../page');

    await expect(AdminClienteNuevoPage()).rejects.toThrow('REDIRECT:/admin/clientes');
  });

  it('redirects content_admin to /admin/clientes', async () => {
    getAdminSessionMock.mockResolvedValue({
      user: { id: 4, email: 'content@mirubro.com', name: 'Content' },
      internal_role: 'content_admin',
      authorized_sections: ['blog'],
    } as any);

    const { default: AdminClienteNuevoPage } = await import('../page');

    await expect(AdminClienteNuevoPage()).rejects.toThrow('REDIRECT:/admin/clientes');
  });

  it('redirects to /admin/login when there is no session at all', async () => {
    getAdminSessionMock.mockResolvedValue(null);

    const { default: AdminClienteNuevoPage } = await import('../page');

    await expect(AdminClienteNuevoPage()).rejects.toThrow('REDIRECT:/admin/login');
    expect(redirectMock).toHaveBeenCalledWith('/admin/login');
  });
});
