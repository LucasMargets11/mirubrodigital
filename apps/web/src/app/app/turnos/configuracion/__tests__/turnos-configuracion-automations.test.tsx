import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// CUSTOMER 07B: la tarjeta de recordatorios automáticos se muestra con
// `manage_settings` + Turnos y solo es editable con `manage_reminder_automations`.

vi.mock('next/navigation', () => ({ redirect: vi.fn() }));
vi.mock('@/lib/auth', () => ({ getSession: vi.fn() }));
vi.mock('@/components/navigation/app-page-header', () => ({ AppPageHeader: () => null }));
vi.mock('@/features/appointments/public-booking-link-card', () => ({ PublicBookingLinkCard: () => null }));
vi.mock('@/features/merchant-payments/mercado-pago-connection-card', () => ({ MercadoPagoConnectionCard: () => null }));
vi.mock('@/features/appointments/reminder-automation-card', () => ({
    ReminderAutomationCard: ({ canManage }: { canManage: boolean }) => (
        <div data-testid="reminder-automation-card">{canManage ? 'editable' : 'read-only'}</div>
    ),
}));

vi.mock('@/features/appointments/reply-to-email-card', () => ({
    ReplyToEmailCard: ({ canManage }: { canManage: boolean }) => (
        <div data-testid="reply-to-email-card">{canManage ? 'editable' : 'read-only'}</div>
    ),
}));

vi.mock('@/features/appointments/communication-automation-card', () => ({
    CommunicationAutomationCard: ({ canManage }: { canManage: boolean }) => (
        <div data-testid="communication-automation-card">{canManage ? 'editable' : 'read-only'}</div>
    ),
}));

import { getSession } from '@/lib/auth';

import TurnosConfiguracionPage from '../page';

function session(role: string, permissions: Record<string, boolean>) {
    return {
        permissions,
        current: { role, business: { public_booking: null } },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any;
}

async function renderAs(role: string, permissions: Record<string, boolean>) {
    vi.mocked(getSession).mockResolvedValue(session(role, permissions));
    render(await TurnosConfiguracionPage({}));
}

describe('Turnos → Configuración: recordatorios automáticos', () => {
    it('owner/admin: editable', async () => {
        await renderAs('owner', { manage_settings: true, view_appointments: true, manage_reminder_automations: true });
        expect(screen.getByTestId('reminder-automation-card')).toHaveTextContent('editable');
        expect(screen.getByTestId('reply-to-email-card')).toHaveTextContent('editable');
        expect(screen.getByTestId('communication-automation-card')).toHaveTextContent('editable');
    });

    it('manager: solo lectura', async () => {
        await renderAs('manager', { manage_settings: true, view_appointments: true, manage_reminder_automations: false });
        expect(screen.getByTestId('reminder-automation-card')).toHaveTextContent('read-only');
        expect(screen.getByTestId('reply-to-email-card')).toHaveTextContent('read-only');
        expect(screen.getByTestId('communication-automation-card')).toHaveTextContent('read-only');
    });

    it('viewer: no la ve', async () => {
        await renderAs('viewer', { view_appointments: true });
        expect(screen.queryByTestId('reminder-automation-card')).not.toBeInTheDocument();
        expect(screen.queryByTestId('reply-to-email-card')).not.toBeInTheDocument();
        expect(screen.queryByTestId('communication-automation-card')).not.toBeInTheDocument();
    });
});
