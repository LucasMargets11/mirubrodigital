import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/admin/notificaciones',
  useRouter: () => ({ push: mockPush }),
}));

vi.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children, ...props }: any) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock('@/lib/admin/notifications', () => ({
  markAdminNotificationRead: vi.fn().mockResolvedValue({
    id: 'notif-1',
    notif_type: 'support_ticket_created',
    severity: 'info',
    title: 'Notif 1',
    message: '',
    status: 'read',
    action_url: '',
    business_id: null,
    business_name: null,
    related_object_type: '',
    related_object_id: '',
    created_at: null,
    read_at: '2025-01-01T00:00:00Z',
    resolved_at: null,
    archived_at: null,
  }),
  archiveAdminNotification: vi.fn().mockResolvedValue({
    id: 'notif-1',
    notif_type: 'support_ticket_created',
    severity: 'info',
    title: 'Notif 1',
    message: '',
    status: 'archived',
    action_url: '',
    business_id: null,
    business_name: null,
    related_object_type: '',
    related_object_id: '',
    created_at: null,
    read_at: null,
    resolved_at: null,
    archived_at: '2025-01-01T00:00:00Z',
  }),
  resolveAdminNotification: vi.fn().mockResolvedValue({
    id: 'notif-1',
    notif_type: 'support_ticket_created',
    severity: 'info',
    title: 'Notif 1',
    message: '',
    status: 'resolved',
    action_url: '',
    business_id: null,
    business_name: null,
    related_object_type: '',
    related_object_id: '',
    created_at: null,
    read_at: null,
    resolved_at: '2025-01-01T00:00:00Z',
    archived_at: null,
  }),
}));

import type { AdminNotificationList } from '@/lib/admin/types';

const mockData: AdminNotificationList = {
  results: [
    {
      id: 'notif-1',
      notif_type: 'support_ticket_created',
      severity: 'warning',
      title: 'Nuevo ticket abierto',
      message: 'Un usuario tiene un problema.',
      status: 'unread',
      action_url: '/admin/soporte/1',
      business_id: 'biz-1',
      business_name: 'Test Business',
      related_object_type: 'ticket',
      related_object_id: '1',
      created_at: '2025-01-10T12:00:00Z',
      read_at: null,
      resolved_at: null,
      archived_at: null,
    },
  ],
  total: 1,
  unread_count: 1,
  page: 1,
  page_size: 20,
  total_pages: 1,
};

describe('NotificacionesContent', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders filter bar', async () => {
    const { NotificacionesContent } = await import(
      '@/app/admin/notificaciones/notificaciones-content'
    );
    render(<NotificacionesContent initialData={mockData} initialParams={{}} />);
    // FilterBar renders labels as the default <option> inside each <select>
    // Multiple "Estado" elements expected (filter label + table column header)
    expect(screen.getAllByText('Estado').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Severidad').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Tipo').length).toBeGreaterThanOrEqual(1);
  });

  it('renders notification rows', async () => {
    const { NotificacionesContent } = await import(
      '@/app/admin/notificaciones/notificaciones-content'
    );
    render(<NotificacionesContent initialData={mockData} initialParams={{}} />);
    expect(screen.getByText('Nuevo ticket abierto')).toBeInTheDocument();
    expect(screen.getByText('Test Business')).toBeInTheDocument();
  });

  it('renders empty state when no data', async () => {
    const { NotificacionesContent } = await import(
      '@/app/admin/notificaciones/notificaciones-content'
    );
    const emptyData: AdminNotificationList = {
      ...mockData,
      results: [],
      total: 0,
      unread_count: 0,
    };
    render(<NotificacionesContent initialData={emptyData} initialParams={{}} />);
    expect(screen.getByText('Sin notificaciones')).toBeInTheDocument();
  });

  it('renders empty state when initialData is null', async () => {
    const { NotificacionesContent } = await import(
      '@/app/admin/notificaciones/notificaciones-content'
    );
    render(<NotificacionesContent initialData={null} initialParams={{}} />);
    expect(screen.getByText('Sin notificaciones')).toBeInTheDocument();
  });

  it('calls markAdminNotificationRead when mark-read button clicked', async () => {
    const { markAdminNotificationRead } = await import('@/lib/admin/notifications');
    const { NotificacionesContent } = await import(
      '@/app/admin/notificaciones/notificaciones-content'
    );
    render(<NotificacionesContent initialData={mockData} initialParams={{}} />);

    const readBtn = screen.getByRole('button', { name: /marcar como leída/i });
    fireEvent.click(readBtn);

    await waitFor(() => {
      expect(markAdminNotificationRead).toHaveBeenCalledWith('notif-1');
    });
  });

  it('calls archiveAdminNotification when archive button clicked', async () => {
    const { archiveAdminNotification } = await import('@/lib/admin/notifications');
    const { NotificacionesContent } = await import(
      '@/app/admin/notificaciones/notificaciones-content'
    );
    render(<NotificacionesContent initialData={mockData} initialParams={{}} />);

    const archiveBtn = screen.getByRole('button', { name: /archivar/i });
    fireEvent.click(archiveBtn);

    await waitFor(() => {
      expect(archiveAdminNotification).toHaveBeenCalledWith('notif-1');
    });
  });
});
