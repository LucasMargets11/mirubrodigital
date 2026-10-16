/**
 * CUSTOMER 07C.1 — visibilidad por rol con los hooks reales (react-query).
 * El panel no conoce roles: muestra lo que devuelve la API, que ya filtra por
 * kind en el backend (manager → solo `customer_reminder_due`; viewer → 403).
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { AnchorHTMLAttributes, ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api/client';

import type { BusinessNotification, BusinessNotificationList } from '../types';

vi.mock('next/link', () => ({
    __esModule: true,
    default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
        <a href={href} {...props}>
            {children}
        </a>
    ),
}));

const api = vi.hoisted(() => ({
    fetchBusinessNotifications: vi.fn(),
    markBusinessNotificationRead: vi.fn(),
}));

vi.mock('../api', async (importOriginal) => ({
    ...(await importOriginal<typeof import('../api')>()),
    ...api,
}));

import { BusinessNotificationsPanel } from '../business-notifications-panel';

function reminder(overrides: Partial<BusinessNotification> = {}): BusinessNotification {
    return {
        id: 'n-rem',
        kind: 'customer_reminder_due',
        severity: 'info',
        title: 'Recordatorio: Llamar a Ana',
        message: 'Ana Confirmada',
        action_url: '/app/clientes/c-ana',
        read_at: null,
        created_at: '2026-10-02T10:00:00Z',
        ...overrides,
    };
}

/** Lo que la API devuelve a un manager: solo el kind habilitado por RBAC. */
const managerList: BusinessNotificationList = { results: [reminder()], unread_count: 1 };

function renderPanel() {
    const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    return render(<BusinessNotificationsPanel />, { wrapper });
}

beforeEach(() => {
    api.fetchBusinessNotifications.mockReset();
    api.markBusinessNotificationRead.mockReset();
});

afterEach(() => {
    vi.useRealTimers();
});

describe('BusinessNotificationsPanel por rol (CUSTOMER 07C.1)', () => {
    it('manager: ve el panel con su recordatorio, "Ver cliente" y el conteo visible', async () => {
        api.fetchBusinessNotifications.mockResolvedValue(managerList);
        renderPanel();
        const item = (await screen.findByText('Recordatorio: Llamar a Ana')).closest('li') as HTMLElement;
        expect(within(item).getByRole('link', { name: 'Ver cliente' })).toHaveAttribute('href', '/app/clientes/c-ana');
        expect(screen.getByText('Notificaciones (1)')).toBeInTheDocument();
        expect(screen.queryByText(/turno/i)).not.toBeInTheDocument();
        expect(api.fetchBusinessNotifications).toHaveBeenCalledWith({ unread: true, limit: 5 });
    });

    it('manager: marcar como leída llama al endpoint y refresca la lista', async () => {
        api.fetchBusinessNotifications.mockResolvedValueOnce(managerList).mockResolvedValue({ results: [], unread_count: 0 });
        api.markBusinessNotificationRead.mockResolvedValue(reminder({ read_at: '2026-10-02T10:05:00Z' }));
        renderPanel();
        fireEvent.click(await screen.findByRole('button', { name: 'Marcar como leída' }));
        await waitFor(() => expect(api.markBusinessNotificationRead).toHaveBeenCalled());
        expect(api.markBusinessNotificationRead.mock.calls[0][0]).toBe('n-rem');
        await waitFor(() => expect(screen.queryByText('Recordatorio: Llamar a Ana')).not.toBeInTheDocument());
    });

    it('manager: abrir "Ver cliente" también la marca como leída', async () => {
        api.fetchBusinessNotifications.mockResolvedValue(managerList);
        api.markBusinessNotificationRead.mockResolvedValue(reminder());
        renderPanel();
        fireEvent.click(await screen.findByRole('link', { name: 'Ver cliente' }));
        await waitFor(() => expect(api.markBusinessNotificationRead).toHaveBeenCalled());
        expect(api.markBusinessNotificationRead.mock.calls[0][0]).toBe('n-rem');
    });

    it('viewer (403): no renderiza nada y no reintenta', async () => {
        api.fetchBusinessNotifications.mockRejectedValue(new ApiError('forbidden', 403));
        const { container } = renderPanel();
        await waitFor(() => expect(api.fetchBusinessNotifications).toHaveBeenCalledTimes(1));
        await new Promise((resolve) => setTimeout(resolve, 20));
        expect(api.fetchBusinessNotifications).toHaveBeenCalledTimes(1);
        expect(container).toBeEmptyDOMElement();
    });

    it('owner/admin: siguen viendo todos los kinds que devuelve la API', async () => {
        api.fetchBusinessNotifications.mockResolvedValue({
            unread_count: 2,
            results: [
                reminder(),
                reminder({
                    id: 'n-pay',
                    kind: 'appointment_payment_review',
                    severity: 'critical',
                    title: 'Pago recibido — reserva requiere revisión',
                    action_url: '/app/turnos/turnos?appointment=x',
                }),
            ],
        });
        renderPanel();
        expect(await screen.findByText('Pago recibido — reserva requiere revisión')).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Ver turno' })).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Ver cliente' })).toBeInTheDocument();
        expect(screen.getByText('Notificaciones (2)')).toBeInTheDocument();
    });

    it('polling: vuelve a consultar cada 60 s', async () => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
        api.fetchBusinessNotifications.mockResolvedValue(managerList);
        renderPanel();
        await screen.findByText('Recordatorio: Llamar a Ana');
        expect(api.fetchBusinessNotifications).toHaveBeenCalledTimes(1);
        await act(async () => {
            await vi.advanceTimersByTimeAsync(60_000);
        });
        await waitFor(() => expect(api.fetchBusinessNotifications).toHaveBeenCalledTimes(2));
    });
});
