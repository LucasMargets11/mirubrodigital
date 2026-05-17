import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('next/navigation', () => ({
  usePathname: () => '/admin/notificaciones',
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children, ...props }: any) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

const mockUnreadCount = { count: 3, critical_count: 0 };
const mockList = {
  results: [],
  total: 0,
  unread_count: 3,
  page: 1,
  page_size: 6,
  total_pages: 0,
};

describe('NotificationBell', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn()
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve(mockUnreadCount),
        })
        .mockResolvedValue({
          ok: true,
          json: () => Promise.resolve(mockList),
        }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the bell button', async () => {
    const { NotificationBell } = await import('@/components/admin/notification-bell');
    render(<NotificationBell initialCount={null} />);
    expect(screen.getByRole('button', { name: /notificaciones/i })).toBeInTheDocument();
  });

  it('renders badge when initial count provided', async () => {
    const { NotificationBell } = await import('@/components/admin/notification-bell');
    render(<NotificationBell initialCount={{ count: 5, critical_count: 0 }} />);
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('renders critical badge variant when critical_count > 0', async () => {
    const { NotificationBell } = await import('@/components/admin/notification-bell');
    render(<NotificationBell initialCount={{ count: 2, critical_count: 1 }} />);
    const badge = screen.getByText('2');
    // should have red badge classes
    expect(badge.className).toMatch(/red/);
  });

  it('caps badge display at 99+', async () => {
    const { NotificationBell } = await import('@/components/admin/notification-bell');
    render(<NotificationBell initialCount={{ count: 120, critical_count: 0 }} />);
    expect(screen.getByText('99+')).toBeInTheDocument();
  });

  it('renders no badge when count is 0', async () => {
    const { NotificationBell } = await import('@/components/admin/notification-bell');
    render(<NotificationBell initialCount={{ count: 0, critical_count: 0 }} />);
    expect(screen.queryByText('0')).not.toBeInTheDocument();
  });
});
