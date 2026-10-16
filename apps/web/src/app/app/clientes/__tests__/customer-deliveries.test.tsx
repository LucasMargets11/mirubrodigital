// CUSTOMER 07D.2: sección "Comunicaciones" de la ficha. Solo historial/
// auditoría de entregas externas (hoy con proveedores fake): sin "Enviar".
process.env.TZ = 'America/Argentina/Buenos_Aires';

import { fireEvent, render, screen, within } from '@testing-library/react';
import type { AnchorHTMLAttributes, ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Customer, CustomerDelivery } from '@/features/customers/types';

vi.mock('next/navigation', () => ({ redirect: vi.fn(), useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/lib/auth', () => ({ getSession: vi.fn() }));
vi.mock('next/link', () => ({
    __esModule: true,
    default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
        <a href={href} {...props}>{children}</a>
    ),
}));

const hooks = vi.hoisted(() => ({
    useCustomer: vi.fn(),
    useCustomers: vi.fn(),
    useCustomerAppointments: vi.fn(),
    useCustomerTimeline: vi.fn(),
    useCreateCustomer: vi.fn(),
    useUpdateCustomer: vi.fn(),
    useCustomerNotes: vi.fn(),
    useCreateCustomerNote: vi.fn(),
    useUpdateCustomerNote: vi.fn(),
    useDeleteCustomerNote: vi.fn(),
    useRefreshCustomerAppointmentViews: vi.fn(),
    useCustomerReminders: vi.fn(),
    useCreateCustomerReminder: vi.fn(),
    useUpdateCustomerReminder: vi.fn(),
    useCustomerContactPreferences: vi.fn(),
    useUpdateCustomerContactPreferences: vi.fn(),
    useCustomerDeliveries: vi.fn(),
}));
vi.mock('@/features/customers/hooks', () => hooks);

vi.mock('@/components/ui/modal', () => ({
    Modal: ({ open, title, children, footer }: { open: boolean; title: string; children: ReactNode; footer?: ReactNode }) =>
        open ? (
            <div role="dialog" aria-label={title}>
                {children}
                {footer}
            </div>
        ) : null,
}));

import { getSession } from '@/lib/auth';

import CustomerDetailPage from '../[id]/page';

const getSessionMock = vi.mocked(getSession);

const ANA = {
    id: 'c-ana',
    name: 'Ana QA',
    phone: '11 5555-0202',
    email: 'ana@dominio.com',
    doc_type: null,
    doc_number: null,
    type: 'individual',
    tags: [],
    is_active: true,
    created_at: '2026-09-01T12:00:00Z',
    updated_at: '2026-09-01T12:00:00Z',
} as unknown as Customer;

function delivery(overrides: Partial<CustomerDelivery> = {}): CustomerDelivery {
    return {
        id: 'd-1',
        channel: 'whatsapp',
        channel_display: 'WhatsApp',
        purpose: 'appointment_reminder',
        purpose_display: 'Recordatorio de turno',
        status: 'sent',
        status_display: 'Enviado',
        destination_masked: '•••• 0202',
        attempt_count: 1,
        max_attempts: 3,
        is_simulated: false,
        skip_reason: null,
        failure_code: null,
        appointment_id: null,
        reminder_id: null,
        created_at: '2026-10-03T14:00:00-03:00',
        last_attempt_at: '2026-10-03T14:02:00-03:00',
        next_retry_at: null,
        sent_at: '2026-10-03T14:02:00-03:00',
        delivered_at: null,
        failed_at: null,
        skipped_at: null,
        cancelled_at: null,
        ...overrides,
    };
}

const FAILED_EMAIL = delivery({
    id: 'd-2',
    channel: 'email',
    channel_display: 'Email',
    purpose: 'no_show_followup',
    purpose_display: 'Seguimiento por inasistencia',
    status: 'failed',
    status_display: 'Fallido',
    destination_masked: 'a•••@dominio.com',
    attempt_count: 2,
    failure_code: 'fake_temporary_error',
    sent_at: null,
    failed_at: '2026-10-03T15:10:00-03:00',
    next_retry_at: '2026-10-03T15:15:00-03:00',
});

const SKIPPED = delivery({
    id: 'd-3',
    channel: 'email',
    channel_display: 'Email',
    purpose: 'no_show_followup',
    purpose_display: 'Seguimiento por inasistencia',
    status: 'skipped',
    status_display: 'Omitido',
    destination_masked: 'a•••@dominio.com',
    attempt_count: 0,
    skip_reason: 'consent_missing',
    sent_at: null,
    skipped_at: '2026-10-02T09:30:00-03:00',
});

const OWNER = { view_customers: true, view_appointments: true, manage_customers: true };
const VIEWER = { view_customers: true, view_appointments: true };

let page: { count: number; results: CustomerDelivery[] } = { count: 0, results: [] };

function session(permissions: Record<string, boolean>) {
    return {
        features: { appointments_core: true, customers: true, sales: false, quotes: false, orders: false },
        permissions,
        services: { enabled: ['appointments'] },
        current: { business: { id: 1, name: 'QA', status: 'active', timezone: 'America/Argentina/Buenos_Aires' }, role: 'owner', service: 'appointments' },
    } as any;
}

beforeEach(() => {
    vi.clearAllMocks();
    page = { count: 0, results: [] };
    const empty = { data: { count: 0, next: null, previous: null, results: [] }, isLoading: false, isError: false };
    hooks.useCustomer.mockReturnValue({ data: ANA, isLoading: false });
    hooks.useCustomers.mockReturnValue({ ...empty, refetch: vi.fn() });
    hooks.useCustomerAppointments.mockReturnValue(empty);
    hooks.useCustomerTimeline.mockReturnValue({ data: { count: 0, next: null, previous: null, results: [], types: [] }, isLoading: false, isError: false });
    hooks.useCreateCustomer.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useUpdateCustomer.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useCustomerNotes.mockReturnValue(empty);
    hooks.useCreateCustomerNote.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useUpdateCustomerNote.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useDeleteCustomerNote.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useRefreshCustomerAppointmentViews.mockReturnValue(vi.fn());
    hooks.useCustomerReminders.mockReturnValue({
        data: { count: 0, next: null, previous: null, results: [], counts: { pending: 0, closed: 0 } },
        isLoading: false,
        isError: false,
    });
    hooks.useCreateCustomerReminder.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useUpdateCustomerReminder.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useCustomerContactPreferences.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    hooks.useUpdateCustomerContactPreferences.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useCustomerDeliveries.mockImplementation((_id: string, params: { limit?: number }) => ({
        data: { count: page.count, next: null, previous: null, results: page.results.slice(0, params?.limit ?? 10) },
        isLoading: false,
        isError: false,
    }));
});

async function renderPage(permissions: Record<string, boolean> = OWNER) {
    getSessionMock.mockResolvedValue(session(permissions));
    render(await CustomerDetailPage({ params: Promise.resolve({ id: ANA.id }) }));
}

function section() {
    return screen.getByRole('region', { name: 'Comunicaciones' });
}

function rows() {
    return within(section()).queryAllByTestId('customer-delivery');
}

describe('CUSTOMER 07D.2 · Comunicaciones', () => {
    it('1. empty state, sin botón de envío', async () => {
        await renderPage();
        expect(within(section()).getByText('Todavía no hubo comunicaciones automáticas con este cliente.')).toBeInTheDocument();
        expect(within(section()).queryByRole('button')).not.toBeInTheDocument();
        expect(hooks.useCustomerDeliveries).toHaveBeenCalledWith('c-ana', { limit: 10 });
    });

    it('2. WhatsApp enviado: canal, propósito, estado y fecha', async () => {
        page = { count: 1, results: [delivery()] };
        await renderPage();
        const [row] = rows();
        expect(within(row).getByText('WhatsApp')).toBeInTheDocument();
        expect(within(row).getByText('Recordatorio de turno')).toBeInTheDocument();
        expect(within(row).getByText('Enviado')).toBeInTheDocument();
        expect(within(row).getByText('03 oct · 14:02')).toBeInTheDocument();
        expect(within(row).queryByText('Simulado')).not.toBeInTheDocument();
        expect(within(section()).queryByRole('button', { name: /Enviar/ })).not.toBeInTheDocument();
    });

    it('3/6/7. Email fallido: error resumido, reintento e intentos', async () => {
        page = { count: 1, results: [FAILED_EMAIL] };
        await renderPage();
        const [row] = rows();
        expect(within(row).getByText('Email')).toBeInTheDocument();
        expect(within(row).getByText('Seguimiento por inasistencia')).toBeInTheDocument();
        expect(within(row).getByText('Fallido')).toBeInTheDocument();
        expect(within(row).getByText('Error temporal del proveedor · reintento 03 oct · 15:15')).toBeInTheDocument();
        expect(within(row).getByText('Intentos: 2 de 3')).toBeInTheDocument();
        expect(within(row).getByText('03 oct · 15:10')).toBeInTheDocument();
    });

    it('4. omitido muestra el motivo de negocio, no un error', async () => {
        page = { count: 1, results: [SKIPPED] };
        await renderPage();
        const [row] = rows();
        expect(within(row).getByText('Omitido')).toBeInTheDocument();
        expect(within(row).getByText('Consentimiento inválido')).toBeInTheDocument();
        expect(within(row).getByText('02 oct · 09:30')).toBeInTheDocument();
        expect(within(row).queryByText(/Intentos/)).not.toBeInTheDocument();
        expect(within(row).queryByText(/proveedor/)).not.toBeInTheDocument();
    });

    it('5. destino enmascarado (nunca el completo)', async () => {
        page = { count: 2, results: [delivery(), FAILED_EMAIL] };
        await renderPage();
        const [wa, email] = rows();
        expect(within(wa).getByText('•••• 0202')).toBeInTheDocument();
        expect(within(email).getByText('a•••@dominio.com')).toBeInTheDocument();
        expect(section().textContent).not.toContain('5555-0202');
        expect(section().textContent).not.toContain('ana@dominio.com');
    });

    it('6b. motivos y errores desconocidos usan un texto genérico; simulado se marca', async () => {
        page = {
            count: 2,
            results: [
                delivery({ id: 'x1', status: 'skipped', status_display: 'Omitido', skip_reason: 'nuevo_motivo', attempt_count: 0 }),
                delivery({ id: 'x2', status: 'failed', status_display: 'Fallido', failure_code: 'meta_131026', is_simulated: true }),
            ],
        };
        await renderPage();
        const [skipped, failed] = rows();
        expect(within(skipped).getByText('Omitido por las reglas de contacto')).toBeInTheDocument();
        expect(within(failed).getByText('Error del proveedor')).toBeInTheDocument();
        expect(within(failed).getByText('Simulado')).toBeInTheDocument();
    });

    it('8. paginación: "Ver más comunicaciones" pide la página siguiente', async () => {
        page = { count: 12, results: Array.from({ length: 12 }, (_, i) => delivery({ id: `d-${i}` })) };
        await renderPage();
        expect(rows()).toHaveLength(10);
        fireEvent.click(within(section()).getByRole('button', { name: 'Ver más comunicaciones' }));
        expect(hooks.useCustomerDeliveries).toHaveBeenLastCalledWith('c-ana', { limit: 20 });
        expect(rows()).toHaveLength(12);
        expect(within(section()).queryByRole('button', { name: 'Ver más comunicaciones' })).not.toBeInTheDocument();
    });

    it('9. viewer (solo view_customers) puede leer el historial', async () => {
        page = { count: 1, results: [delivery()] };
        await renderPage(VIEWER);
        expect(rows()).toHaveLength(1);
        expect(within(section()).queryByRole('button')).not.toBeInTheDocument();
    });

    it('10. mobile: filas apiladas y "Ver más" con target táctil de 44px', async () => {
        page = { count: 12, results: Array.from({ length: 12 }, (_, i) => delivery({ id: `d-${i}` })) };
        await renderPage();
        expect(rows()[0].className).toMatch(/flex-col/);
        expect(rows()[0].className).toMatch(/sm:flex-row/);
        expect(within(section()).getByRole('button', { name: 'Ver más comunicaciones' }).className).toMatch(/min-h-11/);
    });

    it('error de carga se informa sin romper la ficha', async () => {
        hooks.useCustomerDeliveries.mockReturnValue({ data: undefined, isLoading: false, isError: true });
        await renderPage();
        expect(within(section()).getByRole('alert')).toHaveTextContent('No pudimos cargar las comunicaciones.');
        expect(screen.getByRole('region', { name: 'Notas internas' })).toBeInTheDocument();
    });
});
