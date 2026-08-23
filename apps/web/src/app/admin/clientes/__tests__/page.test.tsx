import { render } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/admin', () => ({
  getAdminClients: vi.fn(),
  getAdminClientKPIs: vi.fn(),
  getAdminSession: vi.fn(),
}));

let capturedProps: any = null;

vi.mock('../clientes-content', () => ({
  ClientesContent: (props: any) => {
    capturedProps = props;
    return <div data-testid="clientes-content" />;
  },
}));

// eslint-disable-next-line prefer-const
import { getAdminClients, getAdminClientKPIs, getAdminSession } from '@/lib/admin';

const getAdminClientsMock = vi.mocked(getAdminClients);
const getAdminClientKPIsMock = vi.mocked(getAdminClientKPIs);
const getAdminSessionMock = vi.mocked(getAdminSession);

const CLIENT_LIST = { results: [], total: 0, page: 1, page_size: 25, total_pages: 1 };
const KPIS = {
  total_clients: 0, active: 0, trialing: 0, past_due: 0, canceled: 0,
  scheduled_cancel: 0, payment_issues_30d: 0, plan_distribution: [],
};

describe('AdminClientesPage — wiring canCreateClient by role', () => {
  beforeEach(() => {
    capturedProps = null;
    getAdminClientsMock.mockResolvedValue(CLIENT_LIST as any);
    getAdminClientKPIsMock.mockResolvedValue(KPIS as any);
  });

  it('passes canCreateClient=true for superadmin', async () => {
    getAdminSessionMock.mockResolvedValue({
      user: { id: 1, email: 'a@mirubro.com', name: 'A' },
      internal_role: 'superadmin',
      authorized_sections: ['clientes'],
    } as any);

    const { default: AdminClientesPage } = await import('../page');
    const element = await AdminClientesPage({ searchParams: Promise.resolve({}) } as any);
    render(element);

    expect(capturedProps.canCreateClient).toBe(true);
  });

  it('passes canCreateClient=false for operations, but still fetches the list (read access preserved)', async () => {
    getAdminSessionMock.mockResolvedValue({
      user: { id: 2, email: 'ops@mirubro.com', name: 'Ops' },
      internal_role: 'operations',
      authorized_sections: ['clientes'],
    } as any);

    const { default: AdminClientesPage } = await import('../page');
    const element = await AdminClientesPage({ searchParams: Promise.resolve({}) } as any);
    render(element);

    expect(capturedProps.canCreateClient).toBe(false);
    expect(getAdminClientsMock).toHaveBeenCalled();
    expect(capturedProps.initialData).toEqual(CLIENT_LIST);
  });

  it('passes canCreateClient=false when there is no session', async () => {
    getAdminSessionMock.mockResolvedValue(null);

    const { default: AdminClientesPage } = await import('../page');
    const element = await AdminClientesPage({ searchParams: Promise.resolve({}) } as any);
    render(element);

    expect(capturedProps.canCreateClient).toBe(false);
  });
});
