import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { AnchorHTMLAttributes } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Turnos CUSTOMER 02: `/app/clientes` es la superficie canónica compartida
// (Gestión o Turnos). Para un Business solo-Turnos: carga, muestra el resumen
// de Turnos en la ficha, no muestra secciones comerciales y respeta VIEWER.

const nav = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({
    redirect: vi.fn(),
    useRouter: () => ({ push: nav.push }),
}));

vi.mock('next/link', () => ({
    __esModule: true,
    default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
        <a href={href} {...props}>{children}</a>
    ),
}));

vi.mock('@/lib/auth', () => ({ getSession: vi.fn() }));

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
    // CUSTOMER 07A: la ficha monta la sección Recordatorios (vacía por defecto).
    useCustomerReminders: vi.fn(() => ({
        data: { count: 0, next: null, previous: null, results: [], counts: { pending: 0, closed: 0 } },
        isLoading: false,
        isError: false,
    })),
    useCreateCustomerReminder: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
    useUpdateCustomerReminder: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
    // CUSTOMER 07D.1: la ficha monta Preferencias de contacto (defaults).
    useCustomerDeliveries: vi.fn(() => ({ data: { count: 0, next: null, previous: null, results: [] }, isLoading: false, isError: false })),
    useCustomerContactPreferences: vi.fn(() => ({
        data: {
            customer_id: 'x', whatsapp_enabled: false, email_enabled: false, phone_enabled: true, preferred_channel: null,
            do_not_contact: false, whatsapp_consent_at: null, whatsapp_consent_source: null, email_consent_at: null,
            email_consent_source: null, updated_at: null,
            channels: {
                whatsapp: { usable: false, reason: 'disabled' }, email: { usable: false, reason: 'disabled' }, phone: { usable: true, reason: null },
            },
        },
        isLoading: false,
        isError: false,
    })),
    useUpdateCustomerContactPreferences: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
}));
vi.mock('@/features/customers/hooks', () => hooks);

// CUSTOMER 07C: el listado monta el panel de notificaciones del negocio.
const notificationHooks = vi.hoisted(() => ({
    useUnreadBusinessNotifications: vi.fn((): { data: unknown } => ({ data: undefined })),
    useMarkBusinessNotificationRead: vi.fn(() => ({ mutate: vi.fn(), isPending: false, variables: undefined })),
}));
vi.mock('@/features/business-notifications/hooks', () => notificationHooks);

import { ApiError } from '@/lib/api/client';
import { getSession } from '@/lib/auth';

import ClientesPage from '../page';
import CustomerDetailPage from '../[id]/page';
import { CustomersClient } from '../customers-client';
import { CustomerDetailClient } from '../[id]/customer-detail-client';

const getSessionMock = vi.mocked(getSession);

const TURNOS_FEATURES = { appointments_core: true, customers: true, sales: false, quotes: false, dashboard: true };

function turnosSession(permissions: Record<string, boolean>) {
    return {
        features: TURNOS_FEATURES,
        permissions,
        services: { enabled: ['appointments'] },
        current: { business: { id: 1, name: 'Turnos', status: 'active', timezone: 'America/Argentina/Buenos_Aires' }, role: 'owner', service: 'appointments' },
    } as any;
}

const OWNER_PERMS = { view_appointments: true, view_customers: true, manage_customers: true };
const VIEWER_PERMS = { view_appointments: true, view_customers: true };

const CUSTOMER = {
    id: 'c-1',
    name: 'Ana Turnos',
    doc_type: 'dni',
    doc_number: '30111222',
    email: 'ana@example.com',
    phone: '11 5555-0001',
    type: 'individual',
    tax_condition: null,
    address_line: null,
    city: null,
    province: null,
    postal_code: null,
    country: null,
    note: null,
    tags: ['frecuente'],
    is_active: true,
    // 02/10/2026 01:30 UTC = 01/10/2026 22:30 en Buenos Aires.
    created_at: '2026-10-02T01:30:00Z',
    updated_at: '2026-10-02T01:30:00Z',
};

const SUMMARY = {
    total: 6,
    completed: 3,
    cancelled: 1,
    no_show: 1,
    upcoming: 1,
    next_appointment: {
        id: 'a-next',
        start_at: '2026-10-07T13:00:00Z',
        end_at: '2026-10-07T13:30:00Z',
        status: 'confirmed',
        service_name: 'Corte de pelo',
        professional_name: 'Lucía QA',
    },
    last_appointment: {
        id: 'a-last',
        start_at: '2026-09-29T18:00:00Z',
        end_at: '2026-09-29T18:30:00Z',
        status: 'no_show',
        service_name: 'Corte + barba',
        professional_name: null,
    },
};

beforeEach(() => {
    vi.clearAllMocks();
    hooks.useCustomerTimeline.mockReturnValue({
        data: { count: 0, next: null, previous: null, results: [], types: ['appointment'] },
        isLoading: false,
        isError: false,
    });
    hooks.useCustomerAppointments.mockReturnValue({ data: { count: 0, next: null, previous: null, results: [] }, isLoading: false });
    hooks.useCreateCustomer.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    // CUSTOMER 04C: la ficha siempre monta "Notas internas".
    hooks.useCustomerNotes.mockReturnValue({ data: { count: 0, next: null, previous: null, results: [] }, isLoading: false, isError: false });
    hooks.useCreateCustomerNote.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useUpdateCustomerNote.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useDeleteCustomerNote.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useUpdateCustomer.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useCustomers.mockReturnValue({ data: { count: 1, results: [CUSTOMER] }, isLoading: false });
});

describe('/app/clientes para un Business solo-Turnos (appointments_base)', () => {
    it('carga el listado con permisos de gestión para OWNER', async () => {
        getSessionMock.mockResolvedValue(turnosSession(OWNER_PERMS));
        render(await ClientesPage());

        expect(screen.getByText('Ana Turnos')).toBeInTheDocument();
        expect(screen.getByText(/ana@example.com/)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Nuevo cliente' })).toBeInTheDocument();
        expect(screen.queryByText('Tu plan no incluye Clientes')).not.toBeInTheDocument();
    });

    it('muestra el aviso de recordatorio vencido con enlace a la ficha (CUSTOMER 07C)', async () => {
        notificationHooks.useUnreadBusinessNotifications.mockReturnValue({
            data: {
                unread_count: 1,
                results: [
                    {
                        id: 'n-rem',
                        kind: 'customer_reminder_due',
                        severity: 'info',
                        title: 'Recordatorio: Llamar a Ana',
                        message: 'Ana Turnos',
                        action_url: '/app/clientes/c-1',
                        read_at: null,
                        created_at: '2026-10-02T15:00:00Z',
                    },
                ],
            },
        });
        getSessionMock.mockResolvedValue(turnosSession(OWNER_PERMS));
        render(await ClientesPage());
        const panel = screen.getByRole('region', { name: 'Notificaciones' });
        expect(within(panel).getByText('Recordatorio: Llamar a Ana')).toBeInTheDocument();
        expect(within(panel).getByRole('link', { name: 'Ver cliente' })).toHaveAttribute('href', '/app/clientes/c-1');
        notificationHooks.useUnreadBusinessNotifications.mockReturnValue({ data: undefined });
    });

    it('VIEWER ve el listado en solo lectura', async () => {
        getSessionMock.mockResolvedValue(turnosSession(VIEWER_PERMS));
        render(await ClientesPage());

        expect(screen.getByText('Ana Turnos')).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Nuevo cliente' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Editar' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Desactivar' })).not.toBeInTheDocument();
    });

    it('un plan sin Clientes (ni Gestión ni Turnos) sigue bloqueado', async () => {
        getSessionMock.mockResolvedValue({
            ...turnosSession(OWNER_PERMS),
            features: { qr_reviews_core: true, sales: false, customers: false },
        });
        render(await ClientesPage());

        expect(screen.getByText('Tu plan no incluye Clientes')).toBeInTheDocument();
        expect(hooks.useCustomers).not.toHaveBeenCalled();
    });

    it('la fila del listado abre la ficha canónica /app/clientes/<id>', () => {
        render(<CustomersClient canCreate={false} canManage={false} />);
        fireEvent.click(screen.getByText('Ana Turnos'));
        expect(nav.push).toHaveBeenCalledWith('/app/clientes/c-1');
    });
});

describe('Ficha de Cliente con resumen de Turnos', () => {
    it('la página pasa la timezone del Business y oculta Ventas/Presupuestos en Turnos', async () => {
        getSessionMock.mockResolvedValue(turnosSession(OWNER_PERMS));
        hooks.useCustomer.mockReturnValue({ data: { ...CUSTOMER, appointments_summary: SUMMARY }, isLoading: false });
        render(await CustomerDetailPage({ params: Promise.resolve({ id: 'c-1' }) }));

        expect(screen.getByRole('heading', { name: 'Ana Turnos' })).toBeInTheDocument();
        expect(screen.getByRole('region', { name: 'Resumen de Turnos' })).toBeInTheDocument();
        // Sin Gestión: la timeline solo trae Turnos y no hay filtros de Ventas/Presupuestos.
        expect(screen.getByRole('region', { name: 'Historial' })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Ventas' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Presupuestos' })).not.toBeInTheDocument();
    });

    it('renderiza datos base, conteos y próximo/último turno en la zona del Business', () => {
        hooks.useCustomer.mockReturnValue({ data: { ...CUSTOMER, appointments_summary: SUMMARY }, isLoading: false });
        render(
            <CustomerDetailClient
                customerId="c-1"
                canManage
                canViewSales={false}
                canViewQuotes={false}
                businessTimeZone="America/Argentina/Buenos_Aires"
            />,
        );

        expect(screen.getByText('11 5555-0001')).toBeInTheDocument();
        expect(screen.getByText('DNI 30111222')).toBeInTheDocument();
        expect(screen.getByText('frecuente')).toBeInTheDocument();
        expect(screen.getByText('Activo')).toBeInTheDocument();
        expect(screen.getByText('Alta: 01/10/2026')).toBeInTheDocument();

        const region = screen.getByRole('region', { name: 'Resumen de Turnos' });
        const stat = (label: string) => within(region).getByText(label, { selector: 'dt' }).nextElementSibling?.textContent;
        expect(stat('Turnos')).toBe('6');
        expect(stat('Próximos')).toBe('1');
        expect(stat('Completados')).toBe('3');
        expect(stat('Cancelados')).toBe('1');

        // 13:00Z = 10:00 en Buenos Aires; 18:00Z = 15:00.
        expect(within(region).getByText('07/10/2026 10:00')).toBeInTheDocument();
        expect(within(region).getByText('Corte de pelo · Lucía QA')).toBeInTheDocument();
        expect(within(region).getByText('29/09/2026 15:00')).toBeInTheDocument();
        expect(within(region).getByText('Corte + barba')).toBeInTheDocument();
        const links = within(region).getAllByRole('link', { name: 'Ver en agenda' });
        expect(links[0]).toHaveAttribute('href', '/app/turnos/turnos?date=2026-10-07&appointment=a-next');
    });

    it('sin resumen (Gestión sin Turnos) no renderiza la sección ni inventa ceros', () => {
        hooks.useCustomer.mockReturnValue({ data: CUSTOMER, isLoading: false });
        render(<CustomerDetailClient customerId="c-1" canManage={false} canViewSales canViewQuotes={false} />);

        expect(screen.queryByRole('region', { name: 'Resumen de Turnos' })).not.toBeInTheDocument();
        expect(screen.queryByRole('region', { name: 'Próximos turnos' })).not.toBeInTheDocument();
        expect(screen.getByRole('region', { name: 'Historial' })).toBeInTheDocument();
    });

    it('cliente sin turnos muestra estados vacíos', () => {
        hooks.useCustomer.mockReturnValue({
            data: {
                ...CUSTOMER,
                appointments_summary: { ...SUMMARY, total: 0, completed: 0, cancelled: 0, no_show: 0, upcoming: 0, next_appointment: null, last_appointment: null },
            },
            isLoading: false,
        });
        render(<CustomerDetailClient customerId="c-1" canManage={false} canViewSales={false} canViewQuotes={false} />);

        expect(screen.getByText('Sin turnos próximos.')).toBeInTheDocument();
        expect(screen.getByText('Todavía no tuvo turnos.')).toBeInTheDocument();
    });

    it('VIEWER no ve acciones de edición en la ficha', () => {
        hooks.useCustomer.mockReturnValue({ data: { ...CUSTOMER, appointments_summary: SUMMARY }, isLoading: false });
        render(<CustomerDetailClient customerId="c-1" canManage={false} canViewSales={false} canViewQuotes={false} />);

        expect(screen.queryByRole('link', { name: 'Editar cliente' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Editar cliente' })).not.toBeInTheDocument();
        expect(screen.getByRole('link', { name: '← Clientes' })).toHaveAttribute('href', '/app/clientes');
    });
});

describe('Editar cliente desde la ficha (CUSTOMER 02B)', () => {
    function renderDetail(canManage = true) {
        return render(
            <CustomerDetailClient
                customerId="c-1"
                canManage={canManage}
                canViewSales={false}
                canViewQuotes={false}
                businessTimeZone="America/Argentina/Buenos_Aires"
            />,
        );
    }

    it('abre el mismo modal del listado con los datos actuales (no navega a /editar)', () => {
        hooks.useCustomer.mockReturnValue({ data: { ...CUSTOMER, appointments_summary: SUMMARY }, isLoading: false });
        renderDetail();

        const button = screen.getByRole('button', { name: 'Editar cliente' });
        expect(button).not.toHaveAttribute('href');
        fireEvent.click(button);

        const dialog = screen.getByRole('dialog');
        expect(within(dialog).getByRole('heading', { name: 'Editar cliente' })).toBeInTheDocument();
        expect(within(dialog).getByDisplayValue('Ana Turnos')).toBeInTheDocument();
        expect(within(dialog).getByDisplayValue('ana@example.com')).toBeInTheDocument();
        expect(within(dialog).getByDisplayValue('11 5555-0001')).toBeInTheDocument();
        expect(within(dialog).getByDisplayValue('30111222')).toBeInTheDocument();
    });

    it('guardar llama al PATCH existente, cierra el modal y la ficha refleja el cambio sin perder el resumen', async () => {
        let current: Record<string, unknown> = { ...CUSTOMER, appointments_summary: SUMMARY };
        hooks.useCustomer.mockImplementation(() => ({ data: current, isLoading: false }));
        const mutateAsync = vi.fn(async ({ payload }: { payload: Record<string, unknown> }) => {
            // Simula el re-fetch del detalle tras invalidar ['gestion', 'customers'].
            current = { ...current, name: payload.name, phone: payload.phone };
            return current;
        });
        hooks.useUpdateCustomer.mockReturnValue({ mutateAsync, isPending: false });
        renderDetail();

        fireEvent.click(screen.getByRole('button', { name: 'Editar cliente' }));
        const dialog = screen.getByRole('dialog');
        fireEvent.change(within(dialog).getByDisplayValue('Ana Turnos'), { target: { value: '  Ana Editada ' } });
        fireEvent.change(within(dialog).getByDisplayValue('11 5555-0001'), { target: { value: '11 5555-0099' } });
        fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar cambios' }));

        await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
        expect(mutateAsync).toHaveBeenCalledTimes(1);
        expect(mutateAsync).toHaveBeenCalledWith({
            id: 'c-1',
            payload: expect.objectContaining({ name: 'Ana Editada', phone: '11 5555-0099', email: 'ana@example.com', is_active: true }),
        });
        expect(screen.getByRole('heading', { name: 'Ana Editada' })).toBeInTheDocument();
        expect(screen.getByText('11 5555-0099')).toBeInTheDocument();
        expect(screen.getByRole('region', { name: 'Resumen de Turnos' })).toBeInTheDocument();
    });

    it('cancelar cierra sin guardar y descarta lo tipeado', () => {
        hooks.useCustomer.mockReturnValue({ data: { ...CUSTOMER, appointments_summary: SUMMARY }, isLoading: false });
        const mutateAsync = vi.fn();
        hooks.useUpdateCustomer.mockReturnValue({ mutateAsync, isPending: false });
        renderDetail();

        fireEvent.click(screen.getByRole('button', { name: 'Editar cliente' }));
        fireEvent.change(within(screen.getByRole('dialog')).getByDisplayValue('Ana Turnos'), { target: { value: 'Otro' } });
        fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancelar' }));

        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(mutateAsync).not.toHaveBeenCalled();
        expect(screen.getByRole('heading', { name: 'Ana Turnos' })).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: 'Editar cliente' }));
        expect(within(screen.getByRole('dialog')).getByDisplayValue('Ana Turnos')).toBeInTheDocument();
    });

    it('error del API: el modal queda abierto con el mensaje y la ficha no cambia', async () => {
        hooks.useCustomer.mockReturnValue({ data: { ...CUSTOMER, appointments_summary: SUMMARY }, isLoading: false });
        const mutateAsync = vi.fn().mockRejectedValue(
            new ApiError('Bad Request', 400, { email: ['Ingresá un email válido.'] }),
        );
        hooks.useUpdateCustomer.mockReturnValue({ mutateAsync, isPending: false });
        renderDetail();

        fireEvent.click(screen.getByRole('button', { name: 'Editar cliente' }));
        const dialog = screen.getByRole('dialog');
        fireEvent.change(within(dialog).getByDisplayValue('Ana Turnos'), { target: { value: 'Ana Rota' } });
        fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar cambios' }));

        expect(await within(dialog).findByRole('alert')).toHaveTextContent('Ingresá un email válido.');
        expect(screen.getByRole('dialog')).toBeInTheDocument();
        expect(within(dialog).getByDisplayValue('Ana Rota')).toBeInTheDocument();
        expect(screen.getByRole('heading', { name: 'Ana Turnos' })).toBeInTheDocument();
    });

    it('el listado sigue editando con el mismo modal', () => {
        render(<CustomersClient canCreate canManage />);
        fireEvent.click(screen.getByRole('button', { name: 'Editar' }));

        const dialog = screen.getByRole('dialog');
        expect(within(dialog).getByRole('heading', { name: 'Editar cliente' })).toBeInTheDocument();
        expect(within(dialog).getByDisplayValue('Ana Turnos')).toBeInTheDocument();
        expect(nav.push).not.toHaveBeenCalled();
    });
});

// ── CUSTOMER 03: historial de Turnos + modal responsive ─────────────────────

function historyItem(overrides: Record<string, unknown>) {
    return {
        type: 'appointment',
        id: 'h-x',
        occurred_at: '2026-09-28T19:00:00Z',
        start_at: '2026-09-28T19:00:00Z',
        end_at: '2026-09-28T19:30:00Z',
        status: 'completed',
        status_display: 'Completado',
        source: 'manual',
        service_name: 'Coloración',
        service_price: '15000.00',
        professional_id: null,
        professional_name: null,
        customer_name: 'Ana Turnos',
        payment_summary: null,
        created_at: '2026-09-20T12:00:00Z',
        ...overrides,
    };
}

const UPCOMING_ITEMS = [
    historyItem({
        id: 'u-1',
        // 14:15Z = 11:15 en Buenos Aires (vie 02/10/2026).
        start_at: '2026-10-02T14:15:00Z',
        occurred_at: '2026-10-02T14:15:00Z',
        status: 'confirmed',
        status_display: 'Confirmado',
        service_name: 'Corte de pelo',
        professional_name: 'Lucía QA',
        source: 'public',
    }),
];

const HISTORY_ITEMS = [
    historyItem({ id: 'h-1' }),
    historyItem({ id: 'h-2', start_at: '2026-09-12T13:30:00Z', status: 'no_show', status_display: 'No asistió', service_name: 'Corte' }),
    historyItem({ id: 'h-3', start_at: '2026-09-05T13:30:00Z', status: 'cancelled', status_display: 'Cancelado', service_name: 'Barba' }),
];

function page(results: unknown[], count = results.length) {
    return { data: { count, next: null, previous: null, results }, isLoading: false, isError: false };
}

function mockHistory(upcoming: unknown[], history: unknown[], historyCount?: number) {
    hooks.useCustomerAppointments.mockImplementation((_id: string, params: { scope: string }) =>
        params.scope === 'upcoming' ? page(upcoming) : page(history, historyCount),
    );
}

function renderTurnosDetail() {
    hooks.useCustomer.mockReturnValue({ data: { ...CUSTOMER, appointments_summary: SUMMARY }, isLoading: false });
    return render(
        <CustomerDetailClient
            customerId="c-1"
            canManage
            canViewSales={false}
            canViewQuotes={false}
            businessTimeZone="America/Argentina/Buenos_Aires"
        />,
    );
}

describe('Próximos turnos en la ficha (CUSTOMER 03 → 04A)', () => {
    it('pide solo los próximos al endpoint del cliente (lo ocurrido va a la timeline)', () => {
        mockHistory(UPCOMING_ITEMS, HISTORY_ITEMS);
        renderTurnosDetail();

        expect(hooks.useCustomerAppointments).toHaveBeenCalledWith('c-1', { scope: 'upcoming', limit: 25 });
        expect(hooks.useCustomerAppointments).not.toHaveBeenCalledWith('c-1', expect.objectContaining({ scope: 'history' }));
        expect(screen.queryByRole('region', { name: 'Historial de turnos' })).not.toBeInTheDocument();
    });

    it('renderiza fecha en la zona del Business, servicio, profesional y estado', () => {
        mockHistory(UPCOMING_ITEMS, HISTORY_ITEMS);
        renderTurnosDetail();

        const upcoming = screen.getByRole('region', { name: 'Próximos turnos' });
        expect(within(upcoming).getByText('vie 02 oct 2026 · 11:15')).toBeInTheDocument();
        expect(within(upcoming).getByText('Corte de pelo')).toBeInTheDocument();
        expect(within(upcoming).getByText(/Lucía QA/)).toBeInTheDocument();
        expect(within(upcoming).getByText('Confirmado')).toBeInTheDocument();
        expect(within(upcoming).getByText('Reserva online')).toBeInTheDocument();
        expect(within(upcoming).getAllByTestId('customer-appointment')).toHaveLength(1);
    });

    it('sin turnos próximos no duplica la sección: lo dice la tarjeta del resumen', () => {
        mockHistory([], []);
        renderTurnosDetail();

        expect(screen.queryByRole('region', { name: 'Próximos turnos' })).not.toBeInTheDocument();
        const summary = screen.getByRole('region', { name: 'Resumen de Turnos' });
        expect(within(summary).getByText('Próximo turno')).toBeInTheDocument();
    });

    it('"Ver en agenda" usa el deep link existente con el día en la zona del Business', () => {
        mockHistory(UPCOMING_ITEMS, HISTORY_ITEMS);
        renderTurnosDetail();

        const upcoming = screen.getByRole('region', { name: 'Próximos turnos' });
        expect(within(upcoming).getByRole('link', { name: 'Ver en agenda' })).toHaveAttribute(
            'href',
            '/app/turnos/turnos?date=2026-10-02&appointment=u-1',
        );
    });

    it('Gestión sin Turnos (sin appointments_summary) no pide ni muestra turnos', () => {
        hooks.useCustomer.mockReturnValue({ data: CUSTOMER, isLoading: false });
        render(<CustomerDetailClient customerId="c-1" canManage={false} canViewSales canViewQuotes={false} />);

        expect(hooks.useCustomerAppointments).not.toHaveBeenCalled();
        expect(screen.queryByRole('region', { name: 'Próximos turnos' })).not.toBeInTheDocument();
    });
});

describe('CustomerFormModal responsive (CUSTOMER 03)', () => {
    it('header y acciones fijos; solo el cuerpo scrollea y acotado al viewport', () => {
        render(<CustomersClient canCreate canManage />);
        fireEvent.click(screen.getByRole('button', { name: 'Nuevo cliente' }));

        const dialog = screen.getByRole('dialog', { name: 'Nuevo cliente' });
        const panel = within(dialog).getByTestId('modal-panel');
        const header = within(dialog).getByTestId('modal-header');
        const body = within(dialog).getByTestId('modal-body');
        const footer = within(dialog).getByTestId('modal-footer');

        expect(panel.className).toContain('max-h-[calc(100dvh-1rem)]');
        expect(panel.className).toContain('flex-col');
        expect(body.className).toContain('overflow-y-auto');
        expect(body.className).toContain('min-h-0');
        expect(header.className).toContain('shrink-0');
        expect(footer.className).toContain('shrink-0');

        // Campos en el cuerpo; Guardar/Cancelar en el footer, fuera del área que scrollea.
        expect(within(header).getByRole('heading', { name: 'Nuevo cliente' })).toBeInTheDocument();
        expect(within(body).getAllByRole('textbox').length).toBeGreaterThan(3);
        expect(within(footer).getByRole('button', { name: 'Crear cliente' })).toBeInTheDocument();
        expect(within(footer).getByRole('button', { name: 'Cancelar' })).toBeInTheDocument();
        expect(within(body).queryByRole('button', { name: 'Crear cliente' })).not.toBeInTheDocument();
    });

    it('sigue creando con el mismo hook y muestra la validación junto a las acciones', async () => {
        const mutateAsync = vi.fn().mockResolvedValue({ id: 'c-2' });
        hooks.useCreateCustomer.mockReturnValue({ mutateAsync, isPending: false });
        render(<CustomersClient canCreate canManage />);
        fireEvent.click(screen.getByRole('button', { name: 'Nuevo cliente' }));

        const dialog = screen.getByRole('dialog', { name: 'Nuevo cliente' });
        fireEvent.click(within(dialog).getByRole('button', { name: 'Crear cliente' }));
        const footer = within(dialog).getByTestId('modal-footer');
        expect(within(footer).getByRole('alert')).toHaveTextContent('Ingresá el nombre del cliente.');
        expect(mutateAsync).not.toHaveBeenCalled();

        const body = within(dialog).getByTestId('modal-body');
        fireEvent.change(within(body).getAllByRole('textbox')[0], { target: { value: 'Nueva Clienta' } });
        fireEvent.click(within(dialog).getByRole('button', { name: 'Crear cliente' }));
        await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
        expect(mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ name: 'Nueva Clienta' }));
    });
});
