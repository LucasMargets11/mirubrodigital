import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { AnchorHTMLAttributes } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// CUSTOMER 07A: "Recordatorios" en la ficha `/app/clientes/[id]`.
// Lectura con `view_customers`; crear/editar/completar/cancelar solo con
// `manage_customer_reminders` (owner/admin/manager). "Vencido" es derivado
// (`is_overdue` del backend). Fechas en `Business.timezone`. El header abre el
// MISMO formulario que la sección.

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

import { reminderPresets, toRemindAt } from '@/features/customers/reminder-presets';
import type { CustomerReminder } from '@/features/customers/types';
import { ApiError } from '@/lib/api/client';
import { getSession } from '@/lib/auth';

import CustomerDetailPage from '../[id]/page';
import { CustomerReminderFormModal } from '../[id]/customer-reminders';

const getSessionMock = vi.mocked(getSession);
const TZ = 'America/Argentina/Buenos_Aires';
// 15:00Z = 12:00 del viernes 02/10/2026 en Buenos Aires.
const NOW = new Date('2026-10-02T15:00:00Z');

const ANA = {
    id: 'c-ana',
    name: 'Ana QA',
    phone: '11 5555-0001',
    email: null,
    doc_type: null,
    doc_number: null,
    type: 'individual',
    tax_condition: null,
    address_line: null,
    city: null,
    province: null,
    postal_code: null,
    country: null,
    note: null,
    tags: [],
    is_active: true,
    created_at: '2026-09-01T12:00:00Z',
    updated_at: '2026-09-01T12:00:00Z',
    appointments_summary: {
        total: 1,
        upcoming: 1,
        completed: 0,
        cancelled: 0,
        no_show: 0,
        next_appointment: null,
        last_appointment: null,
    },
};

function reminder(overrides: Partial<CustomerReminder> = {}): CustomerReminder {
    return {
        id: 'r-1',
        title: 'Llamar mañana',
        description: '',
        // 19:00Z = 16:00 del sábado 03/10 en Buenos Aires.
        remind_at: '2026-10-03T16:00:00-03:00',
        status: 'pending',
        status_display: 'Pendiente',
        is_overdue: false,
        source: 'manual',
        source_display: 'Manual',
        is_automatic: false,
        appointment_id: null,
        appointment_start_at: null,
        created_by: { id: 'u-1', name: 'Lucía' },
        completed_at: null,
        notified_at: null,
        created_at: '2026-10-02T14:00:00Z',
        updated_at: '2026-10-02T14:00:00Z',
        ...overrides,
    };
}

const OVERDUE = reminder({ id: 'r-0', title: 'Pedir comprobante', remind_at: '2026-10-01T10:00:00-03:00', is_overdue: true });
const UPCOMING = reminder({ id: 'r-1', description: 'Confirmar la seña' });
const DONE = reminder({
    id: 'r-9',
    title: 'Enviar presupuesto',
    status: 'completed',
    status_display: 'Completado',
    remind_at: '2026-09-28T09:00:00-03:00',
    completed_at: '2026-09-28T11:30:00-03:00',
});
const CANCELLED = reminder({ id: 'r-8', title: 'Volver a contactar', status: 'cancelled', status_display: 'Cancelado', remind_at: '2026-09-27T09:00:00-03:00' });

function page(results: CustomerReminder[], counts = { pending: results.length, closed: 0 }) {
    return { data: { count: results.length, next: null, previous: null, results, counts }, isLoading: false, isError: false };
}

const createReminder = vi.fn();
const updateReminder = vi.fn();
let pendingResults: CustomerReminder[] = [];
let closedResults: CustomerReminder[] = [];

const OWNER = { view_customers: true, manage_customers: true, manage_customer_notes: true, manage_customer_reminders: true, view_appointments: true };
const MANAGER = OWNER;
// Gestión: cashier/staff tienen `manage_customers` (POS) pero NO `manage_customer_reminders`.
const CASHIER = { view_customers: true, manage_customers: true };
const VIEWER = { view_customers: true, view_appointments: true };

function session(permissions: Record<string, boolean>) {
    return {
        features: { customers: true, sales: false, quotes: false, orders: false },
        permissions,
        services: { enabled: ['appointments'] },
        current: { business: { id: 1, name: 'QA', status: 'active', timezone: TZ }, role: 'owner', service: 'appointments' },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any;
}

async function renderPage(permissions: Record<string, boolean> = OWNER) {
    getSessionMock.mockResolvedValue(session(permissions));
    render(await CustomerDetailPage({ params: Promise.resolve({ id: ANA.id }) }));
}

function section() {
    return screen.getByRole('region', { name: 'Recordatorios' });
}

function dialog() {
    return screen.getByRole('dialog');
}

beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(NOW);
    pendingResults = [OVERDUE, UPCOMING];
    closedResults = [CANCELLED, DONE];
    hooks.useCustomer.mockReturnValue({ data: ANA, isLoading: false });
    hooks.useCustomerAppointments.mockReturnValue({
        data: {
            count: 1,
            next: null,
            previous: null,
            results: [
                {
                    type: 'appointment',
                    id: 'a-1',
                    occurred_at: '2026-10-10T13:00:00Z',
                    start_at: '2026-10-10T13:00:00Z',
                    end_at: '2026-10-10T13:30:00Z',
                    status: 'confirmed',
                    status_display: 'Confirmado',
                    source: 'manual',
                    service_name: 'Corte',
                    service_price: '1000.00',
                    professional_id: null,
                    professional_name: null,
                    customer_name: 'Ana QA',
                    payment_summary: null,
                    created_at: '2026-10-01T13:00:00Z',
                },
            ],
        },
        isLoading: false,
    });
    hooks.useCustomerTimeline.mockReturnValue({ data: { count: 0, next: null, previous: null, results: [], types: ['appointment'] }, isLoading: false, isError: false });
    hooks.useCreateCustomer.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useUpdateCustomer.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useCustomerNotes.mockReturnValue({ data: { count: 0, next: null, previous: null, results: [] }, isLoading: false, isError: false });
    hooks.useCreateCustomerNote.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useUpdateCustomerNote.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useDeleteCustomerNote.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useRefreshCustomerAppointmentViews.mockReturnValue(vi.fn());
    hooks.useCustomerReminders.mockImplementation((_id: string, params: { scope?: string }, options?: { enabled?: boolean }) => {
        if (params.scope === 'closed') {
            return options?.enabled === false ? { data: undefined, isLoading: false, isError: false } : page(closedResults);
        }
        return page(pendingResults, { pending: pendingResults.length, closed: closedResults.length });
    });
    createReminder.mockResolvedValue(reminder({ id: 'r-new' }));
    updateReminder.mockResolvedValue(reminder());
    hooks.useCreateCustomerReminder.mockReturnValue({ mutateAsync: createReminder, isPending: false });
    hooks.useUpdateCustomerReminder.mockReturnValue({ mutateAsync: updateReminder, isPending: false });
});

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
});

describe('Recordatorios en la ficha (CUSTOMER 07A)', () => {
    it('empty state sin pendientes ni anteriores', async () => {
        pendingResults = [];
        closedResults = [];
        await renderPage();
        expect(within(section()).getByText('No hay recordatorios pendientes.')).toBeInTheDocument();
        expect(within(section()).queryByRole('button', { name: /Ver anteriores/ })).not.toBeInTheDocument();
    });

    it('pide pendientes paginados y NO pide los cerrados hasta expandir', async () => {
        await renderPage();
        expect(hooks.useCustomerReminders).toHaveBeenCalledWith('c-ana', { scope: 'pending', limit: 20 });
        expect(hooks.useCustomerReminders).toHaveBeenCalledWith('c-ana', { scope: 'closed', limit: 10 }, { enabled: false });
    });

    it('renderiza fecha/hora en la zona del Business, descripción y autor', async () => {
        await renderPage();
        const rows = within(within(section()).getByTestId('pending-reminders')).getAllByTestId('customer-reminder');
        expect(rows).toHaveLength(2);
        const upcoming = rows[1];
        expect(within(upcoming).getByText('Llamar mañana')).toBeInTheDocument();
        expect(within(upcoming).getByText('sáb 03 oct 2026 · 16:00')).toBeInTheDocument();
        expect(within(upcoming).getByText('Confirmar la seña')).toBeInTheDocument();
        expect(within(upcoming).getByText(/Creado por Lucía/)).toBeInTheDocument();
        expect(within(upcoming).getByText('Pendiente')).toBeInTheDocument();
    });

    it('marca "Vencido" desde is_overdue (derivado, sin estado nuevo)', async () => {
        await renderPage();
        const [overdue, upcoming] = within(within(section()).getByTestId('pending-reminders')).getAllByTestId('customer-reminder');
        expect(within(overdue).getByText('Vencido')).toBeInTheDocument();
        expect(within(overdue).getByText('jue 01 oct 2026 · 10:00').closest('p')).toHaveClass('text-rose-600');
        expect(within(upcoming).queryByText('Vencido')).not.toBeInTheDocument();
        expect(within(section()).getByText(/1 vencido/)).toBeInTheDocument();
    });

    it('separa pendientes y completados/cancelados detrás de "Ver anteriores"', async () => {
        await renderPage();
        expect(within(section()).queryByTestId('closed-reminders')).not.toBeInTheDocument();
        fireEvent.click(within(section()).getByRole('button', { name: 'Ver anteriores (2)' }));
        const closed = within(section()).getByTestId('closed-reminders');
        const rows = within(closed).getAllByTestId('customer-reminder');
        expect(rows.map((row) => within(row).getAllByText(/./)[0].textContent)).toEqual(['Volver a contactar', 'Enviar presupuesto']);
        expect(within(rows[0]).getByText('Cancelado')).toBeInTheDocument();
        expect(within(rows[1]).getByText('Completado')).toBeInTheDocument();
        expect(within(rows[1]).getByText(/completado lun 28 sep 2026 · 11:30/)).toBeInTheDocument();
        // Los cerrados no tienen acciones (MVP: no se reabren).
        expect(within(closed).queryByRole('button')).not.toBeInTheDocument();
        expect(within(within(section()).getByTestId('pending-reminders')).queryByText('Volver a contactar')).not.toBeInTheDocument();
    });

    it('completar = PATCH status=completed', async () => {
        await renderPage();
        const [overdue] = within(section()).getAllByTestId('customer-reminder');
        fireEvent.click(within(overdue).getByRole('button', { name: 'Marcar como completado' }));
        await waitFor(() => expect(updateReminder).toHaveBeenCalledWith({ reminderId: 'r-0', payload: { status: 'completed' } }));
    });

    it('cancelar pide confirmación y hace PATCH status=cancelled (sin borrar)', async () => {
        await renderPage();
        const [, upcoming] = within(section()).getAllByTestId('customer-reminder');
        fireEvent.click(within(upcoming).getByRole('button', { name: 'Cancelar' }));
        expect(updateReminder).not.toHaveBeenCalled();
        fireEvent.click(within(dialog()).getByRole('button', { name: 'Cancelar recordatorio' }));
        await waitFor(() => expect(updateReminder).toHaveBeenCalledWith({ reminderId: 'r-1', payload: { status: 'cancelled' } }));
        await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
        expect(within(section()).queryByRole('button', { name: /Eliminar/ })).not.toBeInTheDocument();
    });

    it('crea un recordatorio: título, fecha del DatePicker, hora y turno → remind_at sin offset', async () => {
        await renderPage();
        fireEvent.click(within(section()).getByRole('button', { name: '+ Nuevo recordatorio' }));
        const modal = dialog();
        // Default: mañana (en la zona del Business) a las 09:00.
        expect(within(modal).getByRole('button', { name: 'Mañana' })).toHaveAttribute('aria-pressed', 'true');
        fireEvent.change(within(modal).getByLabelText(/Título/), { target: { value: '  Llamar a Ana  ' } });
        fireEvent.click(within(modal).getByRole('button', { name: /Fecha del recordatorio/ }));
        fireEvent.click(document.querySelector('[data-date="2026-10-09"]') as HTMLElement);
        fireEvent.change(within(modal).getByLabelText(/Hora/), { target: { value: '16:30' } });
        fireEvent.change(within(modal).getByLabelText(/Turno relacionado/), { target: { value: 'a-1' } });
        fireEvent.change(within(modal).getByLabelText(/Descripción/), { target: { value: ' Confirmar asistencia ' } });
        fireEvent.click(within(modal).getByRole('button', { name: 'Crear recordatorio' }));
        await waitFor(() =>
            expect(createReminder).toHaveBeenCalledWith({
                title: 'Llamar a Ana',
                description: 'Confirmar asistencia',
                remind_at: '2026-10-09T16:30',
                appointment_id: 'a-1',
            }),
        );
        await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    });

    it('presets rápidos completan fecha y hora editables', async () => {
        await renderPage();
        fireEvent.click(within(section()).getByRole('button', { name: '+ Nuevo recordatorio' }));
        const modal = dialog();
        fireEvent.change(within(modal).getByLabelText(/Título/), { target: { value: 'Llamar' } });
        fireEvent.click(within(modal).getByRole('button', { name: 'En 1 hora' }));
        expect(within(modal).getByLabelText(/Hora/)).toHaveValue('13:00');
        // La hora sigue siendo editable después del preset.
        fireEvent.change(within(modal).getByLabelText(/Hora/), { target: { value: '13:15' } });
        expect(within(modal).getByRole('button', { name: 'En 1 hora' })).toHaveAttribute('aria-pressed', 'false');
        fireEvent.click(within(modal).getByRole('button', { name: 'Crear recordatorio' }));
        await waitFor(() => expect(createReminder).toHaveBeenCalledWith(expect.objectContaining({ remind_at: '2026-10-02T13:15' })));
    });

    it('título vacío no se envía', async () => {
        await renderPage();
        fireEvent.click(within(section()).getByRole('button', { name: '+ Nuevo recordatorio' }));
        expect(within(dialog()).getByRole('button', { name: 'Crear recordatorio' })).toBeDisabled();
        fireEvent.change(within(dialog()).getByLabelText(/Título/), { target: { value: '   ' } });
        expect(within(dialog()).getByRole('button', { name: 'Crear recordatorio' })).toBeDisabled();
        expect(createReminder).not.toHaveBeenCalled();
    });

    it('muestra el error del backend dentro del modal', async () => {
        createReminder.mockRejectedValue(new ApiError('Bad Request', 400, { appointment_id: ['El turno pertenece a otro cliente.'] }));
        await renderPage();
        fireEvent.click(within(section()).getByRole('button', { name: '+ Nuevo recordatorio' }));
        fireEvent.change(within(dialog()).getByLabelText(/Título/), { target: { value: 'Llamar' } });
        fireEvent.click(within(dialog()).getByRole('button', { name: 'Crear recordatorio' }));
        expect(await within(dialog()).findByRole('alert')).toHaveTextContent('El turno pertenece a otro cliente.');
    });

    it('editar precarga fecha/hora en la zona del Business', async () => {
        await renderPage();
        const [, upcoming] = within(section()).getAllByTestId('customer-reminder');
        fireEvent.click(within(upcoming).getByRole('button', { name: 'Editar' }));
        const modal = dialog();
        expect(within(modal).getByLabelText(/Título/)).toHaveValue('Llamar mañana');
        expect(within(modal).getByLabelText(/Hora/)).toHaveValue('16:00');
        expect(within(modal).getByRole('button', { name: /Fecha del recordatorio/ })).toHaveTextContent('sábado, 3 de octubre de 2026');
        fireEvent.click(within(modal).getByRole('button', { name: 'Guardar cambios' }));
        await waitFor(() =>
            expect(updateReminder).toHaveBeenCalledWith({
                reminderId: 'r-1',
                payload: { title: 'Llamar mañana', description: 'Confirmar la seña', remind_at: '2026-10-03T16:00', appointment_id: null },
            }),
        );
    });
});

describe('Recordatorios automáticos (CUSTOMER 07B)', () => {
    const AUTO = reminder({
        id: 'r-auto',
        title: 'Confirmar turno de Ana QA',
        source: 'appointment_upcoming',
        source_display: 'Antes del turno',
        is_automatic: true,
        created_by: null,
        appointment_id: 'a-1',
        // 13:00Z = 10:00 del sábado 10/10 en Buenos Aires.
        appointment_start_at: '2026-10-10T10:00:00-03:00',
        remind_at: '2026-10-09T10:00:00-03:00',
    });

    it('se muestran en la misma sección con badge "Automático" y su turno', async () => {
        pendingResults = [AUTO, UPCOMING];
        await renderPage();
        const [auto, manual] = within(within(section()).getByTestId('pending-reminders')).getAllByTestId('customer-reminder');
        expect(within(auto).getByText('Automático')).toBeInTheDocument();
        expect(within(auto).getByText('vie 09 oct 2026 · 10:00')).toBeInTheDocument();
        expect(within(auto).getByText(/Turno del sáb 10 oct 2026 · 10:00 · Antes del turno/)).toBeInTheDocument();
        expect(within(manual).queryByText('Automático')).not.toBeInTheDocument();
        expect(screen.queryByRole('region', { name: /automátic/i })).not.toBeInTheDocument();
    });

    it('un automático no ofrece Editar pero sí Completar y Cancelar; el manual sigue editable', async () => {
        pendingResults = [AUTO, UPCOMING];
        await renderPage();
        const [auto, manual] = within(section()).getAllByTestId('customer-reminder');
        expect(within(auto).queryByRole('button', { name: 'Editar' })).not.toBeInTheDocument();
        expect(within(auto).getByRole('button', { name: 'Marcar como completado' })).toBeInTheDocument();
        expect(within(auto).getByRole('button', { name: 'Cancelar' })).toBeInTheDocument();
        expect(within(manual).getByRole('button', { name: 'Editar' })).toBeInTheDocument();

        fireEvent.click(within(auto).getByRole('button', { name: 'Marcar como completado' }));
        await waitFor(() => expect(updateReminder).toHaveBeenCalledWith({ reminderId: 'r-auto', payload: { status: 'completed' } }));
        fireEvent.click(within(auto).getByRole('button', { name: 'Cancelar' }));
        fireEvent.click(within(dialog()).getByRole('button', { name: 'Cancelar recordatorio' }));
        await waitFor(() => expect(updateReminder).toHaveBeenCalledWith({ reminderId: 'r-auto', payload: { status: 'cancelled' } }));
    });
});

describe('Aviso interno (CUSTOMER 07C)', () => {
    // Vencido y ya avisado: el aviso NO lo completa.
    const NOTIFIED = reminder({
        id: 'r-avisado',
        title: 'Llamar por inasistencia',
        remind_at: '2026-10-01T10:00:00-03:00',
        is_overdue: true,
        notified_at: '2026-10-01T10:01:00-03:00',
    });

    it('muestra "Vencido · Avisado" sin convertirlo en completado', async () => {
        pendingResults = [NOTIFIED, UPCOMING];
        await renderPage();
        const [notified, upcoming] = within(within(section()).getByTestId('pending-reminders')).getAllByTestId('customer-reminder');
        expect(within(notified).getByText('Vencido')).toBeInTheDocument();
        const badge = within(notified).getByText('Avisado');
        expect(badge).toHaveAttribute('title', 'Aviso enviado al equipo el jue 01 oct 2026 · 10:01');
        expect(within(notified).queryByText('Completado')).not.toBeInTheDocument();
        expect(within(upcoming).queryByText('Avisado')).not.toBeInTheDocument();
        // Sigue contando como pendiente/vencido.
        expect(within(section()).getByText(/1 vencido/)).toBeInTheDocument();
    });

    it('completar y cancelar siguen disponibles en un avisado', async () => {
        pendingResults = [NOTIFIED];
        await renderPage();
        const [row] = within(section()).getAllByTestId('customer-reminder');
        // Un manual avisado se puede seguir editando.
        expect(within(row).getByRole('button', { name: 'Editar' })).toBeInTheDocument();
        fireEvent.click(within(row).getByRole('button', { name: 'Marcar como completado' }));
        await waitFor(() => expect(updateReminder).toHaveBeenCalledWith({ reminderId: 'r-avisado', payload: { status: 'completed' } }));
        fireEvent.click(within(row).getByRole('button', { name: 'Cancelar' }));
        fireEvent.click(within(dialog()).getByRole('button', { name: 'Cancelar recordatorio' }));
        await waitFor(() => expect(updateReminder).toHaveBeenCalledWith({ reminderId: 'r-avisado', payload: { status: 'cancelled' } }));
    });

    it('un cerrado que fue avisado no muestra la marca (solo aplica a pendientes)', async () => {
        closedResults = [{ ...DONE, notified_at: '2026-09-28T09:01:00-03:00' }];
        await renderPage();
        fireEvent.click(within(section()).getByRole('button', { name: /Ver anteriores/ }));
        const [row] = within(within(section()).getByTestId('closed-reminders')).getAllByTestId('customer-reminder');
        expect(within(row).getByText('Completado')).toBeInTheDocument();
        expect(within(row).queryByText('Avisado')).not.toBeInTheDocument();
    });

    it('mobile: las marcas envuelven y las acciones mantienen el target táctil', async () => {
        pendingResults = [{ ...NOTIFIED, source: 'no_show_followup', source_display: 'Seguimiento por inasistencia', is_automatic: true }];
        await renderPage();
        const [row] = within(section()).getAllByTestId('customer-reminder');
        expect(within(row).getByText('Avisado').parentElement).toHaveClass('flex-wrap');
        expect(within(row).getByText('Automático')).toBeInTheDocument();
        expect(within(row).getByRole('button', { name: 'Marcar como completado' })).toHaveClass('min-h-9');
        expect(within(row).getByRole('button', { name: 'Cancelar' })).toHaveClass('min-h-9');
    });
});

describe('Permisos', () => {
    it('viewer: solo lectura (sin alta, completar ni cancelar)', async () => {
        await renderPage(VIEWER);
        expect(within(section()).getAllByTestId('customer-reminder')).toHaveLength(2);
        expect(within(section()).queryByRole('button', { name: '+ Nuevo recordatorio' })).not.toBeInTheDocument();
        expect(within(section()).queryByRole('button', { name: 'Marcar como completado' })).not.toBeInTheDocument();
        expect(within(section()).queryByRole('button', { name: 'Cancelar' })).not.toBeInTheDocument();
        expect(within(section()).queryByRole('button', { name: 'Editar' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Nuevo recordatorio' })).not.toBeInTheDocument();
    });

    it('cashier con manage_customers pero sin manage_customer_reminders: solo lectura', async () => {
        await renderPage(CASHIER);
        expect(within(section()).queryByRole('button', { name: '+ Nuevo recordatorio' })).not.toBeInTheDocument();
        expect(within(section()).queryByRole('button', { name: 'Marcar como completado' })).not.toBeInTheDocument();
    });

    it('manager ve todas las acciones', async () => {
        await renderPage(MANAGER);
        expect(within(section()).getByRole('button', { name: '+ Nuevo recordatorio' })).toBeInTheDocument();
        expect(within(section()).getAllByRole('button', { name: 'Marcar como completado' })).toHaveLength(2);
        expect(within(section()).getAllByRole('button', { name: 'Cancelar' })).toHaveLength(2);
    });
});

describe('Acción rápida del header', () => {
    function toolbar() {
        return screen.getByRole('toolbar', { name: 'Acciones del cliente' });
    }

    it('"Nuevo recordatorio" abre el mismo formulario de la sección (un solo modal)', async () => {
        await renderPage();
        fireEvent.click(within(toolbar()).getByRole('button', { name: 'Nuevo recordatorio' }));
        expect(screen.getAllByRole('dialog')).toHaveLength(1);
        const modal = dialog();
        expect(within(modal).getByRole('heading', { name: 'Nuevo recordatorio' })).toBeInTheDocument();
        fireEvent.change(within(modal).getByLabelText(/Título/), { target: { value: 'Desde el header' } });
        fireEvent.click(within(modal).getByRole('button', { name: 'Crear recordatorio' }));
        await waitFor(() => expect(createReminder).toHaveBeenCalledWith(expect.objectContaining({ title: 'Desde el header', remind_at: '2026-10-03T09:00' })));
        await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    });

    it('no aparece sin manage_customer_reminders', async () => {
        await renderPage(CASHIER);
        expect(within(toolbar()).queryByRole('button', { name: 'Nuevo recordatorio' })).not.toBeInTheDocument();
    });

    it('mobile: queda en el desplegable con target táctil', async () => {
        await renderPage();
        const item = within(screen.getByTestId('customer-secondary-actions')).getByRole('button', { name: 'Nuevo recordatorio' });
        expect(item).toHaveClass('min-h-11', 'w-full');
    });
});

describe('Formulario reutilizable', () => {
    it('acepta un turno preseleccionado (para abrirlo desde Turnos en 07B)', async () => {
        render(
            <CustomerReminderFormModal customerId="c-ana" timeZone={TZ} appointmentId="a-1" appointmentsEnabled onClose={vi.fn()} />,
        );
        expect(screen.getByLabelText(/Turno relacionado/)).toHaveValue('a-1');
        fireEvent.change(screen.getByLabelText(/Título/), { target: { value: 'Confirmar asistencia' } });
        fireEvent.click(screen.getByRole('button', { name: 'Crear recordatorio' }));
        await waitFor(() => expect(createReminder).toHaveBeenCalledWith(expect.objectContaining({ appointment_id: 'a-1' })));
    });

    it('sin Turnos visibles no muestra el campo de turno', () => {
        render(<CustomerReminderFormModal customerId="c-ana" timeZone={TZ} onClose={vi.fn()} />);
        expect(screen.queryByLabelText(/Turno relacionado/)).not.toBeInTheDocument();
    });

    it('mobile: el DatePicker abre como sheet y el formulario apila los campos', () => {
        vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
        render(<CustomerReminderFormModal customerId="c-ana" timeZone={TZ} onClose={vi.fn()} />);
        const hour = screen.getByLabelText(/Hora/);
        expect(hour).toHaveClass('w-full', 'min-h-11');
        expect(hour.closest('.grid')).toHaveClass('sm:grid-cols-[minmax(0,1fr)_9rem]');
        expect(hour.closest('.grid')?.className).not.toMatch(/(^|\s)grid-cols-/);
        fireEvent.click(screen.getByRole('button', { name: /Fecha del recordatorio/ }));
        const sheet = screen.getByRole('dialog', { name: 'Fecha del recordatorio' });
        expect(sheet).toHaveAttribute('aria-modal', 'true');
        // Botones del pie: apilados a ancho completo en mobile.
        expect(screen.getByRole('button', { name: 'Crear recordatorio' }).parentElement).toHaveClass('flex-col-reverse');
    });
});

describe('reminderPresets (zona del Business)', () => {
    it('calcula en Business.timezone aunque en UTC ya sea otro día', () => {
        // 02:30Z del 03/10 = 23:30 del 02/10 en Buenos Aires.
        const presets = reminderPresets(TZ, new Date('2026-10-03T02:30:00Z'));
        expect(presets.map((p) => [p.label, p.date, p.time])).toEqual([
            ['En 1 hora', '2026-10-03', '00:30'],
            ['Mañana', '2026-10-03', '09:00'],
            ['En 3 días', '2026-10-05', '09:00'],
            ['Próxima semana', '2026-10-09', '09:00'],
        ]);
        expect(toRemindAt('2026-10-03', '09:00')).toBe('2026-10-03T09:00');
    });
});
