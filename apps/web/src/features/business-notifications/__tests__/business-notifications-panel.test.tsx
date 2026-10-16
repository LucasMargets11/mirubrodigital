import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AnchorHTMLAttributes } from 'react';

import type { BusinessNotification } from '../types';

vi.mock('next/link', () => ({
    __esModule: true,
    default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
        <a href={href} {...props}>
            {children}
        </a>
    ),
}));

const mutate = vi.fn();
let listData: { results: BusinessNotification[]; unread_count: number } | undefined;

vi.mock('../hooks', () => ({
    useUnreadBusinessNotifications: () => ({ data: listData }),
    useMarkBusinessNotificationRead: () => ({ mutate, isPending: false, variables: undefined }),
}));

import { safeInternalHref } from '../api';
import { BusinessNotificationsPanel } from '../business-notifications-panel';

function notif(overrides: Partial<BusinessNotification> = {}): BusinessNotification {
    return {
        id: 'n1',
        kind: 'appointment_confirmed',
        severity: 'info',
        title: 'Nueva reserva confirmada',
        message: 'Ana · Corte · 05/10/2026 10:00',
        action_url: '/app/turnos/turnos?date=2026-10-05&appointment=abc',
        read_at: null,
        created_at: '2026-10-01T10:00:00Z',
        ...overrides,
    };
}

beforeEach(() => {
    mutate.mockClear();
    listData = undefined;
});

describe('BusinessNotificationsPanel', () => {
    it('no renderiza nada sin notificaciones (o sin permiso)', () => {
        const { container } = render(<BusinessNotificationsPanel />);
        expect(container).toBeEmptyDOMElement();
    });

    it('distingue confirmada de pago en revisión y enlaza al turno', () => {
        listData = {
            unread_count: 2,
            results: [
                notif(),
                notif({
                    id: 'n2',
                    kind: 'appointment_payment_review',
                    severity: 'critical',
                    title: 'Pago recibido — reserva requiere revisión',
                }),
            ],
        };
        render(<BusinessNotificationsPanel />);
        expect(screen.getByText('Nueva reserva confirmada')).toBeInTheDocument();
        const review = screen.getByText('Pago recibido — reserva requiere revisión').closest('li');
        expect(review).toHaveAttribute('data-severity', 'critical');
        const links = screen.getAllByRole('link', { name: 'Ver turno' });
        expect(links[0]).toHaveAttribute('href', '/app/turnos/turnos?date=2026-10-05&appointment=abc');
    });

    it('marcar como leída llama a la mutación con el id', () => {
        listData = { unread_count: 1, results: [notif()] };
        render(<BusinessNotificationsPanel />);
        fireEvent.click(screen.getByRole('button', { name: 'Marcar como leída' }));
        expect(mutate).toHaveBeenCalledWith('n1');
    });

    it('no enlaza URLs externas', () => {
        listData = { unread_count: 1, results: [notif({ action_url: 'https://evil.example/app/' })] };
        render(<BusinessNotificationsPanel />);
        expect(screen.queryByRole('link')).not.toBeInTheDocument();
        expect(safeInternalHref('//evil.example/app/')).toBeNull();
        expect(safeInternalHref('javascript:alert(1)')).toBeNull();
        expect(safeInternalHref('/app/turnos/turnos')).toBe('/app/turnos/turnos');
    });

    it('recordatorio de cliente vencido (CUSTOMER 07C): título, cliente y enlace a la ficha', () => {
        listData = {
            unread_count: 2,
            results: [
                notif({
                    id: 'n-rem',
                    kind: 'customer_reminder_due',
                    title: 'Recordatorio: Llamar por inasistencia',
                    message: 'Ana Confirmada\nPreguntar si reprograma',
                    action_url: '/app/clientes/c-ana',
                }),
                notif(),
            ],
        };
        render(<BusinessNotificationsPanel />);
        const item = screen.getByText('Recordatorio: Llamar por inasistencia').closest('li') as HTMLElement;
        expect(item).toHaveAttribute('data-severity', 'info');
        expect(item).toHaveTextContent('Ana Confirmada');
        const link = within(item).getByRole('link', { name: 'Ver cliente' });
        expect(link).toHaveAttribute('href', '/app/clientes/c-ana');
        // Abrirla la marca como leída (mismo comportamiento que las de Turnos).
        fireEvent.click(link);
        expect(mutate).toHaveBeenCalledWith('n-rem');
        // Las de Turnos siguen diciendo "Ver turno".
        expect(screen.getByRole('link', { name: 'Ver turno' })).toBeInTheDocument();
        expect(screen.getByText('Notificaciones (2)')).toBeInTheDocument();
    });

    it('marcar como leída una de recordatorio usa la misma acción', () => {
        listData = { unread_count: 1, results: [notif({ id: 'n-rem', kind: 'customer_reminder_due', action_url: '/app/clientes/c-ana' })] };
        render(<BusinessNotificationsPanel />);
        fireEvent.click(screen.getByRole('button', { name: 'Marcar como leída' }));
        expect(mutate).toHaveBeenCalledWith('n-rem');
    });
});
