import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

vi.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children, ...props }: any) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

import type { AdminNotification } from '@/lib/admin/types';

const baseNotif: AdminNotification = {
  id: 'notif-001',
  notif_type: 'support_ticket_created',
  severity: 'warning',
  title: 'Nuevo ticket de soporte',
  message: 'Un usuario abrió un ticket.',
  status: 'unread',
  action_url: '/admin/soporte/123',
  business_id: 'biz-1',
  business_name: 'Acme Corp',
  related_object_type: 'ticket',
  related_object_id: '123',
  created_at: '2025-01-15T10:30:00Z',
  read_at: null,
  resolved_at: null,
  archived_at: null,
};

describe('NotificationItem', () => {
  it('renders title and message', async () => {
    const { NotificationItem } = await import('@/components/admin/notification-item');
    render(<NotificationItem notification={baseNotif} />);
    expect(screen.getByText('Nuevo ticket de soporte')).toBeInTheDocument();
    expect(screen.getByText('Un usuario abrió un ticket.')).toBeInTheDocument();
  });

  it('renders business name', async () => {
    const { NotificationItem } = await import('@/components/admin/notification-item');
    render(<NotificationItem notification={baseNotif} />);
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
  });

  it('renders severity badge', async () => {
    const { NotificationItem } = await import('@/components/admin/notification-item');
    render(<NotificationItem notification={baseNotif} />);
    expect(screen.getByText('Advertencia')).toBeInTheDocument();
  });

  it('renders action url link', async () => {
    const { NotificationItem } = await import('@/components/admin/notification-item');
    render(<NotificationItem notification={baseNotif} />);
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/admin/soporte/123');
  });

  it('renders read notif with different styling', async () => {
    const { NotificationItem } = await import('@/components/admin/notification-item');
    const readNotif = { ...baseNotif, status: 'read' as const, read_at: '2025-01-15T11:00:00Z' };
    render(<NotificationItem notification={readNotif} />);
    expect(screen.getByText('Nuevo ticket de soporte')).toBeInTheDocument();
  });

  it('renders critical severity', async () => {
    const { NotificationItem } = await import('@/components/admin/notification-item');
    const critNotif = { ...baseNotif, severity: 'critical' as const };
    render(<NotificationItem notification={critNotif} />);
    expect(screen.getByText('Crítico')).toBeInTheDocument();
  });

  it('renders compact mode without extended content', async () => {
    const { NotificationItem } = await import('@/components/admin/notification-item');
    render(<NotificationItem notification={baseNotif} compact />);
    expect(screen.getByText('Nuevo ticket de soporte')).toBeInTheDocument();
  });

  it('renders custom actions when provided', async () => {
    const { NotificationItem } = await import('@/components/admin/notification-item');
    render(
      <NotificationItem
        notification={baseNotif}
        actions={<button type="button">Archivar</button>}
      />,
    );
    expect(screen.getByRole('button', { name: 'Archivar' })).toBeInTheDocument();
  });
});
