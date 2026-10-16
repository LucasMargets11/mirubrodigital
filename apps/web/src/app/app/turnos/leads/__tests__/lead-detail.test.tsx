// LEADS 05B: detalle operativo `/app/turnos/leads/{id}`. Gating, render,
// atención pendiente, PATCH CRM (estado/resultado/asignación/vínculos), notas,
// historial, solo lectura y errores. La API de Leads está mockeada pero la
// cache de React Query es real (se verifica refetch/invalidación).
process.env.TZ = 'America/Argentina/Buenos_Aires';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { AnchorHTMLAttributes, ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({ redirect: vi.fn(), useRouter: () => ({ push: vi.fn() }) }));

vi.mock('next/link', () => ({
    __esModule: true,
    default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
        <a href={href} {...props}>{children}</a>
    ),
}));

vi.mock('@/lib/auth', () => ({ getSession: vi.fn() }));

vi.mock('@/components/ui/modal', () => ({
    Modal: ({ open, title, children, footer }: { open: boolean; title: string; children: ReactNode; footer?: ReactNode }) =>
        open ? (
            <div role="dialog" aria-label={title}>
                {children}
                {footer}
            </div>
        ) : null,
}));

const leadsApi = vi.hoisted(() => ({
    listLeads: vi.fn(),
    getLead: vi.fn(),
    updateLead: vi.fn(),
    acknowledgeLeadAttention: vi.fn(),
    listLeadAssignees: vi.fn(),
    listLeadNotes: vi.fn(),
    createLeadNote: vi.fn(),
    updateLeadNote: vi.fn(),
    deleteLeadNote: vi.fn(),
    takeoverLead: vi.fn(),
    releaseLead: vi.fn(),
    listLeadMessages: vi.fn(),
    sendLeadMessage: vi.fn(),
}));
vi.mock('@/features/leads/api', () => leadsApi);

const customersDb = vi.hoisted(() => ({
    customers: [] as Array<{ id: string; name: string; phone: string | null; email: string | null; is_active: boolean }>,
    appointments: [] as unknown[],
}));
vi.mock('@/features/customers/hooks', () => ({
    useCustomers: (filters: { search?: string }, options?: { enabled?: boolean }) => {
        if (options?.enabled === false) return { data: undefined, isLoading: false, isError: false, refetch: vi.fn() };
        const term = (filters.search ?? '').toLowerCase();
        const results = customersDb.customers.filter((c) => c.name.toLowerCase().includes(term));
        return { data: { count: results.length, next: null, previous: null, results }, isLoading: false, isError: false, refetch: vi.fn() };
    },
    useCustomer: () => ({ data: undefined, isLoading: false }),
    useCustomerAppointments: (_id: string, _params: unknown, options?: { enabled?: boolean }) =>
        options?.enabled === false
            ? { data: undefined, isLoading: false, isError: false, refetch: vi.fn() }
            : {
                data: { count: customersDb.appointments.length, next: null, previous: null, results: customersDb.appointments },
                isLoading: false,
                isError: false,
                refetch: vi.fn(),
            },
}));

const dayAppointments = vi.hoisted(() => ({ rows: [] as unknown[], calls: [] as unknown[] }));
vi.mock('@/features/appointments/hooks', () => ({
    useAppointments: (params: unknown, options?: { enabled?: boolean }) => {
        if (options?.enabled === false) return { data: undefined, isLoading: false, isError: false, refetch: vi.fn() };
        dayAppointments.calls.push(params);
        return { data: dayAppointments.rows, isLoading: false, isError: false, refetch: vi.fn() };
    },
}));

import { ApiError } from '@/lib/api/client';
import { getSession } from '@/lib/auth';
import type { LeadActivity, LeadConversationControl, LeadDetail, LeadMessage, LeadNote } from '@/features/leads/types';

import LeadDetailPage from '../[id]/page';
import { describeLeadActivity } from '../[id]/lead-activity';
import { LeadDetailClient } from '../[id]/lead-detail-client';

const getSessionMock = vi.mocked(getSession);
const TZ = 'America/Argentina/Buenos_Aires';
const ME = 7;
const ASSIGNEES = [
    { id: 3, display_name: 'Bea Paz' },
    { id: ME, display_name: 'Ana' },
    { id: 9, display_name: 'Ciro Díaz' },
];

function session({ features = {}, permissions = {} }: { features?: Record<string, boolean>; permissions?: Record<string, boolean> }) {
    return {
        user: { id: ME, email: 'ana@example.com', name: 'Ana' },
        features: { appointments_core: true, leads: true, customers: true, ...features },
        permissions: { view_leads: true, ...permissions },
        services: { enabled: ['appointments'] },
        current: { business: { id: 1, name: 'Turnos', status: 'active', timezone: TZ }, role: 'manager', service: 'appointments' },
    } as any;
}

function leadDetail(overrides: Partial<LeadDetail> = {}, agent: Partial<NonNullable<LeadDetail['agent_state']>> = {}): LeadDetail {
    return {
        id: 'lead-1',
        source: 'whatsapp_agent',
        status: 'new',
        outcome: null,
        assigned_to: null,
        customer: null,
        appointment: null,
        needs_attention_at: null,
        needs_attention: false,
        acknowledged_at: null,
        acknowledged_by: null,
        closed_at: null,
        closed_by: null,
        // 05/10/2026 13:00 UTC = 10:00 en Buenos Aires.
        created_at: '2026-10-05T13:00:00Z',
        updated_at: '2026-10-05T13:00:00Z',
        agent_state: {
            // Campos técnicos que el backend sí manda y la UI nunca muestra.
            ...({ agent_instance_id: 'agent-ext-123', external_lead_id: 'ext-lead-999', applied_version: 42 } as object),
            phone_e164: '+5491155550101',
            patient_name: 'Ana Pérez',
            whatsapp_profile_name: 'Anita',
            reason: 'Quiere un turno para corte',
            preferred_time: 'mañana a la tarde',
            urgency: false,
            agent_status: 'active',
            handoff_requested: false,
            handoff_requested_at: null,
            handoff_reasons: [],
            summary: 'Resumen del agente',
            opened_at: '2026-10-05T12:55:00Z',
            closed_at: null,
            last_message_at: '2026-10-05T14:30:00Z',
            ...agent,
        } as LeadDetail['agent_state'],
        conversation_control: null,
        notes: [],
        activity: [],
        ...overrides,
    };
}

function note(id: string, body: string): LeadNote {
    return { id, body, author: { id: '3', name: 'Bea Paz' }, created_at: '2026-10-05T15:00:00Z', updated_at: '2026-10-05T15:00:00Z' };
}

function notesPage(notes: LeadNote[]) {
    return { count: notes.length, next: null, previous: null, results: notes };
}

function messagesPage(messages: LeadMessage[]) {
    return { count: messages.length, next: null, previous: null, results: messages };
}

function activity(overrides: Partial<LeadActivity>): LeadActivity {
    return {
        id: `act-${Math.random()}`,
        kind: 'status_changed',
        kind_display: 'Cambio de estado',
        occurred_at: '2026-10-05T16:00:00Z',
        actor: { id: 3, display_name: 'Bea Paz' },
        previous: null,
        new: null,
        metadata: {},
        ...overrides,
    };
}

let queryClient: QueryClient;

function renderClient(props: Partial<Parameters<typeof LeadDetailClient>[0]> = {}) {
    return render(
        <QueryClientProvider client={queryClient}>
            <LeadDetailClient
                leadId="lead-1"
                canManage
                canViewCustomers
                canViewAppointments
                currentUserId={ME}
                businessTimeZone={TZ}
                {...props}
            />
        </QueryClientProvider>,
    );
}

function badRequest(payload: Record<string, unknown>) {
    return new ApiError('Bad request', 400, payload);
}

beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    leadsApi.getLead.mockResolvedValue(leadDetail());
    leadsApi.listLeadNotes.mockResolvedValue(notesPage([]));
    leadsApi.listLeadAssignees.mockResolvedValue(ASSIGNEES);
    leadsApi.listLeadMessages.mockResolvedValue(messagesPage([]));
    customersDb.customers = [];
    customersDb.appointments = [];
    dayAppointments.rows = [];
    dayAppointments.calls = [];
});

describe('gating de la página', () => {
    it('sin plan / sin view_leads muestra acceso denegado y no renderiza el detalle', async () => {
        getSessionMock.mockResolvedValue(session({ features: { leads: false } }));
        render(await LeadDetailPage({ params: Promise.resolve({ id: 'lead-1' }) }));
        expect(screen.getByText('Tu plan no incluye Leads')).toBeInTheDocument();

        getSessionMock.mockResolvedValue(session({ permissions: { view_leads: false } }));
        render(await LeadDetailPage({ params: Promise.resolve({ id: 'lead-1' }) }));
        expect(screen.getByText('Sin acceso')).toBeInTheDocument();
    });

    it('pasa manage_leads / view_customers / view_appointments de la sesión al cliente', async () => {
        getSessionMock.mockResolvedValue(session({ permissions: { manage_leads: true, view_customers: true, view_appointments: false } }));
        const element = await LeadDetailPage({ params: Promise.resolve({ id: 'lead-9' }) });
        expect(element.props).toMatchObject({
            leadId: 'lead-9',
            canManage: true,
            canViewCustomers: true,
            canViewAppointments: false,
            currentUserId: ME,
            businessTimeZone: TZ,
        });

        getSessionMock.mockResolvedValue(session({}));
        const viewer = await LeadDetailPage({ params: Promise.resolve({ id: 'lead-9' }) });
        expect(viewer.props).toMatchObject({ canManage: false, canViewCustomers: false, canViewAppointments: false });
    });
});

describe('render del detalle', () => {
    it('muestra el resumen operativo sin datos técnicos del agente', async () => {
        leadsApi.getLead.mockResolvedValue(
            leadDetail(
                {
                    status: 'in_progress',
                    assigned_to: { id: 3, display_name: 'Bea Paz' },
                    customer: { id: 'c-1', display_name: 'Ana Cliente' },
                    appointment: {
                        id: 'ap-1',
                        start_at: '2026-10-07T14:00:00Z',
                        end_at: '2026-10-07T14:30:00Z',
                        status: 'cancelled',
                        service_name: 'Corte',
                    },
                },
                {
                    urgency: true,
                    handoff_requested: true,
                    handoff_requested_at: '2026-10-05T14:00:00Z',
                    handoff_reasons: [{ code: 'patient_asked_human', first_at: 'x', last_at: 'y' }, { code: 'nuevo_codigo' }],
                },
            ),
        );
        renderClient();

        expect(await screen.findByRole('heading', { name: 'Ana Pérez' })).toBeInTheDocument();
        expect(screen.getByText('+5491155550101 · Agente de WhatsApp')).toBeInTheDocument();
        expect(screen.getByText('Urgente')).toBeInTheDocument();
        expect(screen.getAllByText('En gestión').length).toBeGreaterThan(0);
        expect(screen.getByText('05/10/2026 10:00')).toBeInTheDocument(); // ingreso
        expect(screen.getByText('05/10/2026 11:30')).toBeInTheDocument(); // último mensaje
        expect(screen.getAllByText('Quiere un turno para corte').length).toBeGreaterThan(0);
        expect(screen.getByText('Resumen del agente')).toBeInTheDocument();
        expect(screen.getByText('mañana a la tarde')).toBeInTheDocument();
        // The header paragraph also carries the handoff_requested_at suffix
        // ("... el <fecha>"), so match the start rather than the exact text
        expect(screen.getByText(/^El paciente pidió una persona/)).toBeInTheDocument();
        expect(screen.getByText('Pidió hablar con una persona')).toBeInTheDocument();
        expect(screen.getByText('El bot derivó la consulta para coordinar un turno')).toBeInTheDocument();
        expect(screen.getByText('Otro motivo')).toBeInTheDocument();

        const customerCard = screen.getByRole('region', { name: 'Cliente' });
        expect(within(customerCard).getByText('Ana Cliente')).toBeInTheDocument();
        expect(within(customerCard).getByRole('link', { name: 'Ver ficha' })).toHaveAttribute('href', '/app/clientes/c-1');

        const appointmentCard = within(screen.getByRole('region', { name: 'Turno' }));
        expect(appointmentCard.getByText('mié 07 oct 2026 · 11:00')).toBeInTheDocument();
        expect(appointmentCard.getByText('Corte')).toBeInTheDocument();
        expect(appointmentCard.getByText('Cancelado')).toBeInTheDocument();
        expect(appointmentCard.getByRole('link', { name: 'Ver en la agenda' })).toHaveAttribute(
            'href',
            '/app/turnos/turnos?date=2026-10-07&appointment=ap-1',
        );

        const text = document.body.textContent ?? '';
        expect(text).not.toContain('agent-ext-123');
        expect(text).not.toContain('ext-lead-999');
        expect(text).not.toContain('nuevo_codigo');
    });

    it('motivo de handoff solo del bot (sin pedido del paciente): no dice "pidió una persona"', async () => {
        leadsApi.getLead.mockResolvedValue(
            leadDetail(
                {},
                {
                    handoff_requested: true,
                    handoff_requested_at: '2026-10-05T14:00:00Z',
                    handoff_reasons: [{ code: 'lead_ready', first_at: 'x', last_at: 'y' }],
                },
            ),
        );
        renderClient();

        expect(await screen.findByText('El bot derivó la consulta para coordinar un turno')).toBeInTheDocument();
        expect(screen.getByText('La consulta está lista para que la tome el equipo')).toBeInTheDocument();
        expect(screen.queryByText('El paciente pidió una persona')).not.toBeInTheDocument();
        expect(screen.queryByText('Pidió hablar con una persona')).not.toBeInTheDocument();
    });

    it('nombre no confirmado: usa el de perfil de WhatsApp pero lo aclara, nunca lo afirma como confirmado', async () => {
        leadsApi.getLead.mockResolvedValue(leadDetail({}, { patient_name: null, whatsapp_profile_name: 'Anita' }));
        renderClient();

        expect(await screen.findByRole('heading', { name: 'Anita' })).toBeInTheDocument();
        expect(screen.getByText('Nombre de perfil de WhatsApp, sin confirmar')).toBeInTheDocument();
        expect(screen.queryByText('Nombre confirmado por el paciente')).not.toBeInTheDocument();
    });

    it('nombre confirmado por el paciente: no muestra la aclaración de "sin confirmar"', async () => {
        leadsApi.getLead.mockResolvedValue(leadDetail());
        renderClient();

        expect(await screen.findByRole('heading', { name: 'Ana Pérez' })).toBeInTheDocument();
        expect(screen.queryByText('Nombre de perfil de WhatsApp, sin confirmar')).not.toBeInTheDocument();
        expect(screen.getByText('Nombre confirmado por el paciente')).toBeInTheDocument();
    });

    it('404 muestra "no encontrado" sin reintentar; 403 muestra sin permiso; otro error permite reintentar', async () => {
        leadsApi.getLead.mockRejectedValue(new ApiError('Not found', 404, { detail: 'No encontrado.' }));
        const { unmount } = renderClient();
        expect(await screen.findByText(/No encontramos este lead/)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Reintentar' })).not.toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Volver a la bandeja' })).toHaveAttribute('href', '/app/turnos/leads');
        expect(leadsApi.getLead).toHaveBeenCalledTimes(1);
        unmount();

        queryClient.clear();
        leadsApi.getLead.mockRejectedValue(new ApiError('Forbidden', 403, { detail: 'x' }));
        const second = renderClient();
        expect(await screen.findByText('No tenés permiso para ver este lead.')).toBeInTheDocument();
        second.unmount();

        queryClient.clear();
        leadsApi.getLead.mockReset();
        leadsApi.getLead.mockRejectedValueOnce(new ApiError('Boom', 500)).mockResolvedValue(leadDetail());
        renderClient();
        fireEvent.click(await screen.findByRole('button', { name: 'Reintentar' }));
        expect(await screen.findByRole('heading', { name: 'Ana Pérez' })).toBeInTheDocument();
    });
});

describe('abrir WhatsApp', () => {
    it('lead de WhatsApp con teléfono válido: link wa.me en pestaña nueva, sin mensaje', async () => {
        renderClient();
        const link = await screen.findByRole('link', { name: 'Abrir WhatsApp' });
        expect(link).toHaveAttribute('href', 'https://wa.me/5491155550101');
        expect(link).toHaveAttribute('target', '_blank');
        expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
        expect(link.getAttribute('href')).not.toContain('text=');
    });

    it('normaliza el teléfono: sin espacios, símbolos ni formato visual', async () => {
        leadsApi.getLead.mockResolvedValue(leadDetail({}, { phone_e164: ' +54 (11) 5555-0101 ' }));
        renderClient();
        const link = await screen.findByRole('link', { name: 'Abrir WhatsApp' });
        // Además agrega el 9 móvil argentino que WhatsApp necesita.
        expect(link).toHaveAttribute('href', 'https://wa.me/5491155550101');
    });

    it('canal no WhatsApp: no ofrece la acción', async () => {
        leadsApi.getLead.mockResolvedValue(leadDetail({ source: 'web_form' as LeadDetail['source'] }));
        renderClient();
        expect(await screen.findByRole('heading', { name: 'Ana Pérez' })).toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Abrir WhatsApp' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Abrir WhatsApp' })).not.toBeInTheDocument();
    });

    it('lead sin teléfono utilizable: acción deshabilitada con explicación', async () => {
        for (const lead of [leadDetail({}, { phone_e164: '' }), leadDetail({ agent_state: null, customer: { id: 'c-1', display_name: 'Ana' } })]) {
            leadsApi.getLead.mockResolvedValue(lead);
            const { unmount } = renderClient();
            const button = await screen.findByRole('button', { name: 'Abrir WhatsApp' });
            expect(button).toBeDisabled();
            expect(button).toHaveAccessibleDescription('No hay un teléfono válido para abrir el chat.');
            expect(screen.queryByRole('link', { name: 'Abrir WhatsApp' })).not.toBeInTheDocument();
            unmount();
            queryClient.clear();
        }
    });
});

describe('atención pendiente', () => {
    const pending = () =>
        leadDetail({ needs_attention: true, needs_attention_at: '2026-10-05T14:00:00Z', status: 'in_progress' });

    it('manage_leads reconoce la atención: actualiza el detalle y refresca la bandeja', async () => {
        leadsApi.getLead.mockResolvedValue(pending());
        const acknowledged = leadDetail({
            needs_attention: false,
            needs_attention_at: '2026-10-05T14:00:00Z',
            acknowledged_at: '2026-10-05T16:00:00Z',
            acknowledged_by: { id: ME, display_name: 'Ana' },
            status: 'in_progress',
            activity: [activity({ kind: 'attention_acknowledged', actor: { id: ME, display_name: 'Ana' } })],
        });
        leadsApi.acknowledgeLeadAttention.mockResolvedValue(acknowledged);
        const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
        renderClient();

        const alert = await screen.findByTestId('lead-attention');
        expect(within(alert).getByText('Este lead pide la atención de una persona')).toBeInTheDocument();
        expect(within(alert).getByText(/Desde 05\/10\/2026 11:00/)).toBeInTheDocument();
        fireEvent.click(within(alert).getByRole('button', { name: 'Marcar como atendido' }));

        await waitFor(() => expect(screen.queryByTestId('lead-attention')).not.toBeInTheDocument());
        expect(leadsApi.acknowledgeLeadAttention).toHaveBeenCalledWith('lead-1');
        expect(screen.getByText('Reconoció el pedido de atención')).toBeInTheDocument();
        expect(invalidate).toHaveBeenCalledWith({ queryKey: ['appointments', 'leads', 'list'] });
    });

    it('ack idempotente (200 sin cambios porque ya estaba reconocido) no muestra error', async () => {
        leadsApi.getLead.mockResolvedValue(pending());
        leadsApi.acknowledgeLeadAttention.mockResolvedValue(
            leadDetail({ needs_attention: false, needs_attention_at: '2026-10-05T14:00:00Z', acknowledged_at: '2026-10-05T15:00:00Z' }),
        );
        renderClient();
        fireEvent.click(await screen.findByRole('button', { name: 'Marcar como atendido' }));
        await waitFor(() => expect(screen.queryByTestId('lead-attention')).not.toBeInTheDocument());
        expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });

    it('muestra el error del backend si el ack falla', async () => {
        leadsApi.getLead.mockResolvedValue(pending());
        leadsApi.acknowledgeLeadAttention.mockRejectedValue(badRequest({ non_field_errors: ['El lead está cerrado.'] }));
        renderClient();
        fireEvent.click(await screen.findByRole('button', { name: 'Marcar como atendido' }));
        expect(await screen.findByText('El lead está cerrado.')).toBeInTheDocument();
        expect(screen.getByTestId('lead-attention')).toBeInTheDocument();
    });

    it('view_leads sin manage ve la alerta pero no la acción', async () => {
        leadsApi.getLead.mockResolvedValue(pending());
        renderClient({ canManage: false });
        const alert = await screen.findByTestId('lead-attention');
        expect(within(alert).queryByRole('button')).not.toBeInTheDocument();
    });
});

describe('estado y resultado', () => {
    it('pasa de nuevo a en gestión con PATCH {status}', async () => {
        leadsApi.updateLead.mockResolvedValue(leadDetail({ status: 'in_progress' }));
        renderClient();
        fireEvent.click(await screen.findByRole('button', { name: 'Pasar a en gestión' }));
        await waitFor(() => expect(leadsApi.updateLead).toHaveBeenCalledWith('lead-1', { status: 'in_progress' }));
        await waitFor(() => expect(screen.queryByRole('button', { name: 'Pasar a en gestión' })).not.toBeInTheDocument());
    });

    it('cerrar exige resultado antes de enviar y manda status+outcome', async () => {
        leadsApi.updateLead.mockResolvedValue(
            leadDetail({ status: 'closed', outcome: 'booked', closed_at: '2026-10-05T17:00:00Z', closed_by: { id: ME, display_name: 'Ana' } }),
        );
        renderClient();
        fireEvent.click(await screen.findByRole('button', { name: 'Cerrar lead' }));
        const dialog = screen.getByRole('dialog', { name: 'Cerrar lead' });
        const submit = within(dialog).getByRole('button', { name: 'Cerrar lead' });
        expect(submit).toBeDisabled();
        expect(within(dialog).getByText('El resultado es obligatorio para cerrar.')).toBeInTheDocument();

        fireEvent.change(within(dialog).getByLabelText('Resultado'), { target: { value: 'booked' } });
        fireEvent.click(submit);

        await waitFor(() => expect(leadsApi.updateLead).toHaveBeenCalledWith('lead-1', { status: 'closed', outcome: 'booked' }));
        await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
        const management = screen.getByRole('region', { name: 'Gestión' });
        expect(within(management).getByText('Cerrado · Turno agendado')).toBeInTheDocument();
        expect(within(management).getByText('Cerrado el 05/10/2026 14:00 por Ana')).toBeInTheDocument();
        // Sin reabrir: no hay acciones de estado, solo cambiar resultado.
        expect(within(management).queryByRole('button', { name: 'Cerrar lead' })).not.toBeInTheDocument();
        expect(within(management).queryByRole('button', { name: 'Pasar a en gestión' })).not.toBeInTheDocument();
        expect(within(management).getByRole('button', { name: 'Cambiar resultado' })).toBeInTheDocument();
    });

    it('muestra el error del backend en el modal si la transición es inválida', async () => {
        leadsApi.updateLead.mockRejectedValue(badRequest({ status: 'Transición de estado no permitida.' }));
        renderClient();
        fireEvent.click(await screen.findByRole('button', { name: 'Cerrar lead' }));
        const dialog = screen.getByRole('dialog', { name: 'Cerrar lead' });
        fireEvent.change(within(dialog).getByLabelText('Resultado'), { target: { value: 'spam' } });
        fireEvent.click(within(dialog).getByRole('button', { name: 'Cerrar lead' }));
        expect(await within(dialog).findByText('Transición de estado no permitida.')).toBeInTheDocument();
    });

    it('en un lead cerrado solo cambia el outcome (PATCH {outcome})', async () => {
        leadsApi.getLead.mockResolvedValue(leadDetail({ status: 'closed', outcome: 'other', closed_at: '2026-10-05T17:00:00Z' }));
        leadsApi.updateLead.mockResolvedValue(leadDetail({ status: 'closed', outcome: 'duplicate', closed_at: '2026-10-05T17:00:00Z' }));
        renderClient();
        fireEvent.click(await screen.findByRole('button', { name: 'Cambiar resultado' }));
        const dialog = screen.getByRole('dialog', { name: 'Cambiar resultado' });
        expect(within(dialog).getByRole('button', { name: 'Guardar resultado' })).toBeDisabled();
        fireEvent.change(within(dialog).getByLabelText('Resultado'), { target: { value: 'duplicate' } });
        fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar resultado' }));
        await waitFor(() => expect(leadsApi.updateLead).toHaveBeenCalledWith('lead-1', { outcome: 'duplicate' }));
    });
});

describe('asignación (LEADS 05B.1: selector con /leads/assignees/)', () => {
    function management() {
        return screen.getByRole('region', { name: 'Gestión' });
    }

    it('carga los asignables del backend y no muestra a nadie más', async () => {
        renderClient();
        const select = await screen.findByRole('combobox', { name: 'Asignar a' });
        expect(leadsApi.listLeadAssignees).toHaveBeenCalledTimes(1);
        const labels = within(select).getAllByRole('option').map((option) => option.textContent);
        expect(labels).toEqual(['Elegí una persona…', 'Bea Paz', 'Ana (vos)', 'Ciro Díaz']);
        expect(within(management()).getByText('Sin asignar')).toBeInTheDocument();
    });

    it('asigna a cualquier candidato', async () => {
        leadsApi.updateLead.mockResolvedValueOnce(leadDetail({ assigned_to: { id: 9, display_name: 'Ciro Díaz' } }));
        renderClient();
        fireEvent.change(await screen.findByRole('combobox', { name: 'Asignar a' }), { target: { value: '9' } });
        await waitFor(() => expect(leadsApi.updateLead).toHaveBeenCalledWith('lead-1', { assigned_to: 9 }));
        const select = await within(management()).findByRole('combobox', { name: 'Reasignar a' });
        expect(select).toHaveValue('9');
        expect(within(management()).getByText('Ciro Díaz', { selector: 'p' })).toBeInTheDocument();
    });

    it('reasigna desde la persona actual y desasigna con PATCH null', async () => {
        leadsApi.getLead.mockResolvedValue(leadDetail({ assigned_to: { id: 3, display_name: 'Bea Paz' } }));
        leadsApi.updateLead.mockResolvedValueOnce(leadDetail({ assigned_to: { id: 9, display_name: 'Ciro Díaz' } }));
        renderClient();
        const select = await screen.findByRole('combobox', { name: 'Reasignar a' });
        expect(select).toHaveValue('3');
        // Sin placeholder: la persona actual es una opción válida.
        expect(within(select).queryByText('Elegí una persona…')).not.toBeInTheDocument();
        fireEvent.change(select, { target: { value: '9' } });
        await waitFor(() => expect(leadsApi.updateLead).toHaveBeenCalledWith('lead-1', { assigned_to: 9 }));

        leadsApi.updateLead.mockResolvedValueOnce(leadDetail({ assigned_to: null }));
        fireEvent.click(await within(management()).findByRole('button', { name: 'Quitar asignación' }));
        await waitFor(() => expect(leadsApi.updateLead).toHaveBeenLastCalledWith('lead-1', { assigned_to: null }));
        expect(await within(management()).findByRole('combobox', { name: 'Asignar a' })).toHaveValue('');
    });

    it('usuario actual: "Asignarme" manda mi id y desaparece una vez asignado', async () => {
        leadsApi.updateLead.mockResolvedValueOnce(leadDetail({ assigned_to: { id: ME, display_name: 'Ana' } }));
        renderClient();
        fireEvent.click(await screen.findByRole('button', { name: 'Asignarme' }));
        await waitFor(() => expect(leadsApi.updateLead).toHaveBeenCalledWith('lead-1', { assigned_to: ME }));
        expect(await within(management()).findByText('Ana (vos)', { selector: 'p' })).toBeInTheDocument();
        expect(within(management()).queryByRole('button', { name: 'Asignarme' })).not.toBeInTheDocument();
        expect(within(management()).queryByRole('button', { name: 'Tomar el lead' })).not.toBeInTheDocument();
    });

    it('asignado a otra persona ofrece "Tomar el lead"; si no estoy entre los asignables no hay atajo', async () => {
        leadsApi.getLead.mockResolvedValue(leadDetail({ assigned_to: { id: 3, display_name: 'Bea Paz' } }));
        const { unmount } = renderClient();
        expect(await screen.findByRole('button', { name: 'Tomar el lead' })).toBeInTheDocument();
        unmount();

        queryClient.clear();
        leadsApi.listLeadAssignees.mockResolvedValue(ASSIGNEES.filter((person) => person.id !== ME));
        renderClient();
        await screen.findByRole('combobox', { name: 'Reasignar a' });
        expect(screen.queryByRole('button', { name: 'Tomar el lead' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Asignarme' })).not.toBeInTheDocument();
    });

    it('asignado que ya no figura entre los asignables: placeholder + aviso, sin inventar la opción', async () => {
        leadsApi.getLead.mockResolvedValue(leadDetail({ assigned_to: { id: 42, display_name: 'Dora Ex' } }));
        renderClient();
        const select = await screen.findByRole('combobox', { name: 'Reasignar a' });
        expect(select).toHaveValue('');
        expect(within(select).queryByText(/Dora Ex/)).not.toBeInTheDocument();
        expect(screen.getByText(/Dora Ex ya no figura entre las personas asignables/)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Quitar asignación' })).toBeInTheDocument();
    });

    it('muestra el error del backend y refresca la lista de asignables', async () => {
        leadsApi.updateLead.mockRejectedValue(badRequest({ assigned_to: ['La persona no tiene acceso a Leads.'] }));
        renderClient();
        fireEvent.change(await screen.findByRole('combobox', { name: 'Asignar a' }), { target: { value: '3' } });
        expect(await screen.findByText('La persona no tiene acceso a Leads.')).toBeInTheDocument();
        await waitFor(() => expect(leadsApi.listLeadAssignees).toHaveBeenCalledTimes(2));
    });

    it('loading local: el detalle y las demás acciones no esperan la lista', async () => {
        leadsApi.listLeadAssignees.mockReturnValue(new Promise(() => { }));
        leadsApi.getLead.mockResolvedValue(leadDetail({ assigned_to: { id: 3, display_name: 'Bea Paz' } }));
        renderClient();
        await screen.findByRole('heading', { name: 'Ana Pérez' });
        expect(within(management()).getByRole('status')).toHaveTextContent('Cargando personas asignables…');
        expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Pasar a en gestión' })).toBeEnabled();
        expect(screen.getByRole('button', { name: 'Quitar asignación' })).toBeEnabled();
    });

    it('error local con reintento; quitar asignación sigue disponible', async () => {
        leadsApi.getLead.mockResolvedValue(leadDetail({ assigned_to: { id: 3, display_name: 'Bea Paz' } }));
        leadsApi.listLeadAssignees.mockRejectedValueOnce(new ApiError('Server error', 500, {}));
        renderClient();
        await screen.findByRole('heading', { name: 'Ana Pérez' });
        const alert = await within(management()).findByRole('alert');
        expect(alert).toHaveTextContent('No pudimos cargar las personas asignables.');
        expect(screen.getByRole('button', { name: 'Quitar asignación' })).toBeEnabled();

        fireEvent.click(within(alert).getByRole('button', { name: 'Reintentar' }));
        expect(await screen.findByRole('combobox', { name: 'Reasignar a' })).toHaveValue('3');
    });

    it('lista vacía: lo indica y no ofrece selector', async () => {
        leadsApi.listLeadAssignees.mockResolvedValue([]);
        renderClient();
        expect(await screen.findByText('No hay personas con acceso a Leads para asignar.')).toBeInTheDocument();
        expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    });
});

describe('vínculo con Customer', () => {
    it('busca un Customer existente (sin alta) y lo vincula', async () => {
        customersDb.customers = [{ id: 'c-9', name: 'Carla Gómez', phone: '1155', email: null, is_active: true }];
        leadsApi.updateLead.mockResolvedValue(leadDetail({ customer: { id: 'c-9', display_name: 'Carla Gómez' } }));
        renderClient();
        const card = await screen.findByRole('region', { name: 'Cliente' });
        fireEvent.click(within(card).getByRole('button', { name: 'Vincular cliente' }));
        expect(within(card).getByText('Escribí al menos 2 caracteres para buscar un cliente existente.')).toBeInTheDocument();
        fireEvent.change(within(card).getByPlaceholderText(/Buscar cliente/), { target: { value: 'Car' } });
        fireEvent.click(await within(card).findByRole('button', { name: /Carla Gómez/ }));
        expect(within(card).queryByText('+ Crear nuevo cliente')).not.toBeInTheDocument();

        await waitFor(() => expect(leadsApi.updateLead).toHaveBeenCalledWith('lead-1', { customer: 'c-9' }));
        expect(await within(card).findByRole('link', { name: 'Ver ficha' })).toHaveAttribute('href', '/app/clientes/c-9');
    });

    it('desvincula con PATCH {customer: null} y muestra errores 400', async () => {
        leadsApi.getLead.mockResolvedValue(leadDetail({ customer: { id: 'c-1', display_name: 'Ana Cliente' } }));
        leadsApi.updateLead.mockRejectedValueOnce(badRequest({ customer: ['El cliente no existe en este negocio.'] }));
        renderClient();
        const card = await screen.findByRole('region', { name: 'Cliente' });
        fireEvent.click(within(card).getByRole('button', { name: 'Desvincular' }));
        expect(await within(card).findByText('El cliente no existe en este negocio.')).toBeInTheDocument();

        leadsApi.updateLead.mockResolvedValueOnce(leadDetail({ customer: null }));
        fireEvent.click(within(card).getByRole('button', { name: 'Desvincular' }));
        await waitFor(() => expect(within(card).getByText('Sin cliente vinculado')).toBeInTheDocument());
        expect(leadsApi.updateLead).toHaveBeenLastCalledWith('lead-1', { customer: null });
    });

    it('sin view_customers no ofrece buscar ni ver la ficha', async () => {
        leadsApi.getLead.mockResolvedValue(leadDetail({ customer: { id: 'c-1', display_name: 'Ana Cliente' } }));
        renderClient({ canViewCustomers: false });
        const card = await screen.findByRole('region', { name: 'Cliente' });
        expect(within(card).queryByRole('button', { name: 'Cambiar cliente' })).not.toBeInTheDocument();
        expect(within(card).queryByRole('link', { name: 'Ver ficha' })).not.toBeInTheDocument();
        expect(within(card).getByRole('button', { name: 'Desvincular' })).toBeInTheDocument();
    });
});

describe('vínculo con Appointment', () => {
    it('elige un turno del cliente o de la agenda del día (cualquier estado) y lo vincula', async () => {
        leadsApi.getLead.mockResolvedValue(leadDetail({ customer: { id: 'c-1', display_name: 'Ana Cliente' } }));
        customersDb.appointments = [
            { id: 'ap-past', start_at: '2026-10-01T13:00:00Z', service_name: 'Color', customer_name: 'Ana Cliente', status: 'no_show' },
        ];
        dayAppointments.rows = [
            { id: 'ap-day', start_at: '2026-10-05T18:00:00Z', service_name: 'Corte', customer_name: 'Otro', status: 'pending_payment', effective_status: 'expired' },
        ];
        leadsApi.updateLead.mockResolvedValue(
            leadDetail({
                customer: { id: 'c-1', display_name: 'Ana Cliente' },
                appointment: { id: 'ap-past', start_at: '2026-10-01T13:00:00Z', end_at: null, status: 'no_show', service_name: 'Color' },
            }),
        );
        renderClient();
        fireEvent.click(await screen.findByRole('button', { name: 'Vincular turno' }));
        const dialog = screen.getByRole('dialog', { name: 'Vincular turno' });

        const customerSection = within(dialog).getByRole('region', { name: 'Turnos del cliente' });
        expect(within(customerSection).getByText('No asistió')).toBeInTheDocument();
        const daySection = within(dialog).getByRole('region', { name: 'Turnos por día' });
        expect(within(daySection).getByText('Vencido')).toBeInTheDocument(); // estado efectivo
        expect(dayAppointments.calls.at(-1)).toEqual({ date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/) });

        fireEvent.click(within(customerSection).getByTestId('lead-appointment-option'));
        await waitFor(() => expect(leadsApi.updateLead).toHaveBeenCalledWith('lead-1', { appointment: 'ap-past' }));
        await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
        expect(within(screen.getByRole('region', { name: 'Turno' })).getByText('No asistió')).toBeInTheDocument();
    });

    it('error 400 queda en el modal; desvincular manda null', async () => {
        leadsApi.getLead.mockResolvedValue(
            leadDetail({ appointment: { id: 'ap-1', start_at: '2026-10-07T14:00:00Z', end_at: null, status: 'confirmed', service_name: 'Corte' } }),
        );
        dayAppointments.rows = [
            { id: 'ap-2', start_at: '2026-10-05T18:00:00Z', service_name: 'Corte', customer_name: 'Otro', status: 'confirmed', effective_status: 'confirmed' },
        ];
        leadsApi.updateLead.mockRejectedValueOnce(badRequest({ appointment: ['El turno no existe en este negocio.'] }));
        renderClient();
        fireEvent.click(await screen.findByRole('button', { name: 'Cambiar turno' }));
        const dialog = screen.getByRole('dialog', { name: 'Vincular turno' });
        expect(within(dialog).queryByRole('region', { name: 'Turnos del cliente' })).not.toBeInTheDocument();
        fireEvent.click(within(dialog).getByTestId('lead-appointment-option'));
        expect(await within(dialog).findByText('El turno no existe en este negocio.')).toBeInTheDocument();
        fireEvent.click(within(dialog).getByRole('button', { name: 'Cancelar' }));

        leadsApi.updateLead.mockResolvedValueOnce(leadDetail({ appointment: null }));
        const card = screen.getByRole('region', { name: 'Turno' });
        fireEvent.click(within(card).getByRole('button', { name: 'Desvincular' }));
        await waitFor(() => expect(within(card).getByText('Sin turno vinculado')).toBeInTheDocument());
        expect(leadsApi.updateLead).toHaveBeenLastCalledWith('lead-1', { appointment: null });
    });
});

describe('notas', () => {
    it('lista newest-first (orden del backend), crea, edita y borra refrescando la lista', async () => {
        leadsApi.listLeadNotes.mockResolvedValue(notesPage([note('n2', 'Segunda'), note('n1', 'Primera')]));
        renderClient();
        const section = await screen.findByRole('region', { name: 'Notas internas' });
        await waitFor(() => expect(within(section).getAllByTestId('lead-note')).toHaveLength(2));
        expect(within(section).getAllByTestId('lead-note')[0]).toHaveTextContent('Segunda');

        leadsApi.createLeadNote.mockResolvedValue(note('n3', 'Nueva'));
        leadsApi.listLeadNotes.mockResolvedValue(notesPage([note('n3', 'Nueva'), note('n2', 'Segunda'), note('n1', 'Primera')]));
        fireEvent.click(within(section).getByRole('button', { name: '+ Agregar nota' }));
        const createDialog = screen.getByRole('dialog', { name: 'Nueva nota interna' });
        fireEvent.change(within(createDialog).getByLabelText('Nota'), { target: { value: '  Nueva  ' } });
        fireEvent.click(within(createDialog).getByRole('button', { name: 'Agregar nota' }));
        await waitFor(() => expect(leadsApi.createLeadNote).toHaveBeenCalledWith('lead-1', 'Nueva'));
        await waitFor(() => expect(within(section).getAllByTestId('lead-note')).toHaveLength(3));

        leadsApi.updateLeadNote.mockResolvedValue(note('n3', 'Editada'));
        fireEvent.click(within(section).getAllByRole('button', { name: 'Editar' })[0]);
        const editDialog = screen.getByRole('dialog', { name: 'Editar nota' });
        fireEvent.change(within(editDialog).getByLabelText('Nota'), { target: { value: 'Editada' } });
        fireEvent.click(within(editDialog).getByRole('button', { name: 'Guardar cambios' }));
        await waitFor(() => expect(leadsApi.updateLeadNote).toHaveBeenCalledWith('lead-1', 'n3', 'Editada'));

        leadsApi.deleteLeadNote.mockResolvedValue(undefined);
        fireEvent.click(within(section).getAllByRole('button', { name: 'Eliminar' })[0]);
        fireEvent.click(within(screen.getByRole('dialog', { name: '¿Eliminar esta nota?' })).getByRole('button', { name: 'Eliminar nota' }));
        await waitFor(() => expect(leadsApi.deleteLeadNote).toHaveBeenCalledWith('lead-1', 'n3'));
        // Cada mutación re-pide las notas (invalidación real de la cache).
        await waitFor(() => expect(leadsApi.listLeadNotes.mock.calls.length).toBeGreaterThanOrEqual(4));
    });

    it('vacío, error al guardar y error al cargar', async () => {
        renderClient();
        const section = await screen.findByRole('region', { name: 'Notas internas' });
        expect(await within(section).findByText('Todavía no hay notas para este lead.')).toBeInTheDocument();

        leadsApi.createLeadNote.mockRejectedValue(badRequest({ body: ['La nota no puede estar vacía.'] }));
        fireEvent.click(within(section).getByRole('button', { name: '+ Agregar nota' }));
        const dialog = screen.getByRole('dialog', { name: 'Nueva nota interna' });
        fireEvent.change(within(dialog).getByLabelText('Nota'), { target: { value: 'x' } });
        fireEvent.click(within(dialog).getByRole('button', { name: 'Agregar nota' }));
        expect(await within(dialog).findByText('La nota no puede estar vacía.')).toBeInTheDocument();
    });

    it('error al cargar las notas', async () => {
        leadsApi.listLeadNotes.mockRejectedValue(new ApiError('Boom', 500));
        renderClient();
        expect(await screen.findByText(/No pudimos cargar las notas/)).toBeInTheDocument();
    });
});

describe('historial', () => {
    it('traduce eventos a texto humano con actor y fecha, sin JSON crudo', async () => {
        leadsApi.getLead.mockResolvedValue(
            leadDetail({
                activity: [
                    activity({
                        kind: 'closed',
                        previous: { value: 'in_progress', label: 'En gestión' },
                        new: { value: 'closed', label: 'Cerrado' },
                        metadata: { outcome: { value: 'booked', label: 'Turno agendado' } },
                    }),
                    activity({ kind: 'reassigned', previous: { id: 3, display_name: 'Bea Paz' }, new: { id: 9, display_name: null } }),
                    activity({
                        kind: 'appointment_linked',
                        new: { id: 'ap-1', start_at: '2026-10-07T14:00:00Z', end_at: null, status: 'completed', service_name: 'Corte' },
                    }),
                    activity({ kind: 'customer_unlinked', previous: { id: 'c-1', display_name: null }, actor: null }),
                ],
            }),
        );
        renderClient();
        const section = await screen.findByRole('region', { name: 'Historial' });
        const items = within(section).getAllByTestId('lead-activity');
        expect(items[0]).toHaveTextContent('Cerró el lead · Resultado: Turno agendado');
        expect(items[0]).toHaveTextContent('Bea Paz · 05/10/2026 13:00');
        expect(items[1]).toHaveTextContent('Reasignó el lead de Bea Paz a una persona que ya no está en el equipo');
        expect(items[2]).toHaveTextContent('Vinculó el turno del mié 07 oct 2026 · 11:00 (Corte)');
        expect(items[2]).toHaveTextContent('Completado');
        expect(items[3]).toHaveTextContent('Desvinculó al cliente un cliente eliminado');
        expect(items[3]).toHaveTextContent('Usuario eliminado');
        expect(section.textContent).not.toMatch(/ap-1|c-1|\{|"value"/);
    });

    // Regression (2026-10-08 QA): `takeover_applied` is the agent's OWN async
    // confirmation (no human ever "did" it, see services/takeover.py's
    // `_record_activity` for the applied/failed kinds — it never passes
    // `actor=`), so a null actor there must never read as "Usuario eliminado"
    // (a deleted real person) next to a header that correctly says "Tomada
    // por vos" for the SAME takeover.
    it('no llama "Usuario eliminado" a la confirmación automática del agente (sin actor humano)', async () => {
        leadsApi.getLead.mockResolvedValue(
            leadDetail({
                activity: [
                    activity({ kind: 'takeover_requested', kind_display: 'Toma de conversación solicitada', actor: { id: 2, display_name: 'QA Admin' } }),
                    activity({ kind: 'takeover_applied', kind_display: 'Conversación tomada (bot pausado)', actor: null }),
                ],
            }),
        );
        renderClient();
        const section = await screen.findByRole('region', { name: 'Historial' });
        const items = within(section).getAllByTestId('lead-activity');
        expect(items[0]).toHaveTextContent('QA Admin');
        expect(items[1]).toHaveTextContent('Confirmación automática del agente');
        expect(section.textContent).not.toContain('Usuario eliminado');
    });

    it('describeLeadActivity cubre todos los tipos', () => {
        const user = (name: string) => ({ id: 1, display_name: name });
        const cases: Array<[Partial<LeadActivity>, string]> = [
            [{ kind: 'status_changed', previous: { value: 'new', label: 'Nuevo' }, new: { value: 'in_progress', label: 'En gestión' } }, 'Cambió el estado de Nuevo a En gestión'],
            [{ kind: 'closed', metadata: {} }, 'Cerró el lead'],
            [{ kind: 'outcome_changed', previous: { value: 'other', label: 'Otro' }, new: { value: 'spam', label: 'Spam' } }, 'Cambió el resultado de Otro a Spam'],
            [{ kind: 'assigned', new: user('Bea') }, 'Asignó el lead a Bea'],
            [{ kind: 'unassigned', previous: user('Bea') }, 'Quitó la asignación a Bea'],
            [{ kind: 'customer_linked', new: { id: 'c', display_name: 'Ana' } }, 'Vinculó al cliente Ana'],
            [{ kind: 'customer_changed', previous: { id: 'c', display_name: 'Ana' }, new: { id: 'd', display_name: 'Eva' } }, 'Cambió el cliente de Ana a Eva'],
            [{ kind: 'appointment_unlinked', previous: { id: 'a', start_at: null, end_at: null, status: null, service_name: null } }, 'Desvinculó un turno eliminado'],
            [{ kind: 'attention_acknowledged' }, 'Reconoció el pedido de atención'],
            [{ kind: 'algo_nuevo', kind_display: 'Algo nuevo' }, 'Algo nuevo'],
        ];
        for (const [overrides, expected] of cases) {
            expect(describeLeadActivity(activity(overrides), TZ)).toBe(expected);
        }
    });

    it('vacío', async () => {
        renderClient();
        expect(await screen.findByText('Todavía no hay cambios registrados en este lead.')).toBeInTheDocument();
    });
});

describe('solo lectura (view_leads sin manage_leads)', () => {
    it('no muestra ninguna acción de gestión, vínculos ni notas', async () => {
        leadsApi.getLead.mockResolvedValue(
            leadDetail({
                assigned_to: { id: 3, display_name: 'Bea Paz' },
                customer: { id: 'c-1', display_name: 'Ana Cliente' },
                appointment: { id: 'ap-1', start_at: '2026-10-07T14:00:00Z', end_at: null, status: 'confirmed', service_name: 'Corte' },
            }),
        );
        leadsApi.listLeadNotes.mockResolvedValue(notesPage([note('n1', 'Primera')]));
        renderClient({ canManage: false });
        await screen.findByRole('heading', { name: 'Ana Pérez' });
        await screen.findByText('Primera');

        for (const name of [
            'Pasar a en gestión', 'Cerrar lead', 'Asignarme', 'Tomar el lead', 'Quitar asignación', 'Cambiar cliente',
            'Desvincular', 'Cambiar turno', '+ Agregar nota', 'Editar', 'Eliminar',
        ]) {
            expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
        }
        // Sin selector de asignación ni pedido de asignables.
        expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
        expect(leadsApi.listLeadAssignees).not.toHaveBeenCalled();
        // Navegación de lectura sigue disponible.
        expect(screen.getByRole('link', { name: 'Ver ficha' })).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Ver en la agenda' })).toBeInTheDocument();
    });

    it('un 403 en una mutación (permiso revocado) se muestra en la tarjeta', async () => {
        leadsApi.updateLead.mockRejectedValue(new ApiError('Forbidden', 403, {}));
        renderClient();
        fireEvent.click(await screen.findByRole('button', { name: 'Pasar a en gestión' }));
        expect(await screen.findByText('No tenés permiso para realizar esta acción.')).toBeInTheDocument();
    });
});

// ── MIRUBRO TAKEOVER 05B: control humano de la conversación ─────────────────

function control(overrides: Partial<LeadConversationControl> = {}): LeadConversationControl {
    return {
        available: true,
        state: 'active',
        command_version: 0,
        last_action: null,
        taken_at: null,
        taken_by: null,
        released_at: null,
        last_error_code: null,
        ...overrides,
    };
}

function withControl(overrides: Partial<LeadConversationControl> = {}) {
    return leadDetail({ conversation_control: control(overrides) });
}

// 05/10/2026 15:00 UTC = 12:00 en Buenos Aires.
const TAKEN: Partial<LeadConversationControl> = {
    state: 'taken',
    command_version: 1,
    last_action: 'takeover',
    taken_at: '2026-10-05T15:00:00Z',
    taken_by: { id: 3, display_name: 'Bea Paz' },
};

async function confirmInDialog(title: string, button: string) {
    const dialog = await screen.findByRole('dialog', { name: title });
    fireEvent.click(within(dialog).getByRole('button', { name: button }));
    return dialog;
}

describe('control de la conversación (TAKEOVER 05B)', () => {
    it('sin conversación del agente (control null) no muestra el bloque y conserva Abrir WhatsApp', async () => {
        renderClient();
        await screen.findByRole('heading', { name: 'Ana Pérez' });
        expect(screen.queryByTestId('lead-conversation-control')).not.toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Abrir WhatsApp' })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Tomar conversación' })).not.toBeInTheDocument();
    });

    it('active: confirma y pide takeover; muestra el pending que devuelve el backend (no taken)', async () => {
        leadsApi.getLead
            .mockResolvedValueOnce(withControl())
            .mockResolvedValue(withControl({ state: 'takeover_pending', command_version: 1, last_action: 'takeover' }));
        leadsApi.takeoverLead.mockResolvedValue({ ok: true, state: 'takeover_pending', command_version: 1 });
        renderClient();

        const block = await screen.findByTestId('lead-conversation-control');
        expect(within(block).getByText('Bot habilitado')).toBeInTheDocument();
        expect(within(block).getByRole('link', { name: 'Abrir WhatsApp' })).toBeInTheDocument();

        // Cancelar no pide nada.
        fireEvent.click(within(block).getByRole('button', { name: 'Tomar conversación' }));
        const dialog = await screen.findByRole('dialog', { name: '¿Tomar esta conversación?' });
        expect(dialog).toHaveTextContent('El bot dejará de responder mensajes nuevos en este chat hasta que vuelvas a habilitarlo.');
        expect(dialog.textContent).not.toMatch(/MiRubro/);
        fireEvent.click(within(dialog).getByRole('button', { name: 'Cancelar' }));
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(leadsApi.takeoverLead).not.toHaveBeenCalled();

        fireEvent.click(within(block).getByRole('button', { name: 'Tomar conversación' }));
        await confirmInDialog('¿Tomar esta conversación?', 'Tomar conversación');

        // Estado del refetch (no el botón del modal mientras el POST está en vuelo).
        expect(await screen.findByText('Estamos pausando el bot.')).toBeInTheDocument();
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Tomando conversación…' })).toBeDisabled();
        expect(screen.queryByText('Conversación tomada')).not.toBeInTheDocument();
        expect(leadsApi.takeoverLead).toHaveBeenCalledTimes(1);
        expect(leadsApi.takeoverLead).toHaveBeenCalledWith('lead-1');
        expect(leadsApi.releaseLead).not.toHaveBeenCalled();
    });

    it('takeover_pending: botón deshabilitado y polling hasta taken (aviso una sola vez)', async () => {
        leadsApi.getLead
            .mockResolvedValueOnce(withControl({ state: 'takeover_pending', command_version: 1, last_action: 'takeover' }))
            .mockResolvedValue(withControl(TAKEN));
        renderClient();

        expect(await screen.findByRole('button', { name: 'Tomando conversación…' })).toBeDisabled();
        expect(screen.queryByRole('button', { name: 'Tomar conversación' })).not.toBeInTheDocument();
        expect(screen.getByText('Procesando')).toBeInTheDocument();

        // Refetch automático (entrega async): sin intervención llega el ACK.
        expect(await screen.findByText('Conversación tomada', {}, { timeout: 6000 })).toBeInTheDocument();
        expect(screen.getAllByText('Conversación tomada.')).toHaveLength(1);
        expect(leadsApi.getLead.mock.calls.length).toBeGreaterThanOrEqual(2);
        expect(leadsApi.takeoverLead).not.toHaveBeenCalled();
    }, 10_000);

    it('taken: muestra quién la tomó, Abrir WhatsApp y Reanudar bot; abrir WhatsApp no toma ni libera', async () => {
        leadsApi.getLead.mockResolvedValue(withControl(TAKEN));
        renderClient();

        const block = await screen.findByTestId('lead-conversation-control');
        expect(within(block).getByText('Conversación tomada')).toBeInTheDocument();
        expect(within(block).getByText('Tomada por Bea Paz · desde 05/10/2026 12:00. El bot está pausado.')).toBeInTheDocument();
        const whatsapp = within(block).getByRole('link', { name: 'Abrir WhatsApp' });
        expect(within(block).getAllByRole('button').map((b) => b.textContent)).toEqual(['Reanudar bot']);

        fireEvent.click(whatsapp);
        expect(leadsApi.takeoverLead).not.toHaveBeenCalled();
        expect(leadsApi.releaseLead).not.toHaveBeenCalled();
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('taken por el usuario actual: "Tomada por vos"', async () => {
        leadsApi.getLead.mockResolvedValue(withControl({ ...TAKEN, taken_by: { id: ME, display_name: 'Ana' } }));
        renderClient();
        expect(await screen.findByText(/Tomada por vos/)).toBeInTheDocument();
    });

    it('Reanudar bot: confirma con la semántica real del agente y queda release_pending', async () => {
        leadsApi.getLead
            .mockResolvedValueOnce(withControl(TAKEN))
            .mockResolvedValue(withControl({ ...TAKEN, state: 'release_pending', command_version: 2, last_action: 'release' }));
        leadsApi.releaseLead.mockResolvedValue({ ok: true, state: 'release_pending', command_version: 2 });
        renderClient();

        fireEvent.click(await screen.findByRole('button', { name: 'Reanudar bot' }));
        const dialog = await screen.findByRole('dialog', { name: '¿Reanudar el bot?' });
        expect(dialog).toHaveTextContent('El bot volverá a responder a partir del próximo mensaje nuevo del paciente.');
        expect(dialog).toHaveTextContent('Los mensajes recibidos mientras la conversación estuvo tomada no serán respondidos retroactivamente.');
        fireEvent.click(within(dialog).getByRole('button', { name: 'Reanudar bot' }));

        expect(await screen.findByText('Estamos devolviendo la conversación al bot.')).toBeInTheDocument();
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Reanudando bot…' })).toBeDisabled();
        expect(leadsApi.releaseLead).toHaveBeenCalledTimes(1);
        expect(leadsApi.releaseLead).toHaveBeenCalledWith('lead-1');
        expect(leadsApi.takeoverLead).not.toHaveBeenCalled();
    });

    it('release_pending: polling hasta active y vuelve a ofrecer Tomar conversación', async () => {
        leadsApi.getLead
            .mockResolvedValueOnce(withControl({ ...TAKEN, state: 'release_pending', command_version: 2, last_action: 'release' }))
            .mockResolvedValue(withControl({ state: 'active', command_version: 2, last_action: 'release', released_at: '2026-10-05T16:00:00Z' }));
        renderClient();

        expect(await screen.findByRole('button', { name: 'Reanudando bot…' })).toBeDisabled();
        expect(await screen.findByText('Bot habilitado', {}, { timeout: 6000 })).toBeInTheDocument();
        expect(screen.getByText('Bot reanudado.')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Tomar conversación' })).toBeEnabled();
    }, 10_000);

    it('error de takeover: copy amigable (sin código crudo) y Reintentar tomar conversación', async () => {
        leadsApi.getLead.mockResolvedValue(withControl({ state: 'error', command_version: 1, last_action: 'takeover', last_error_code: 'network_error' }));
        leadsApi.takeoverLead.mockResolvedValue({ ok: true, state: 'takeover_pending', command_version: 2 });
        renderClient();

        const block = await screen.findByTestId('lead-conversation-control');
        expect(within(block).getByRole('alert')).toHaveTextContent('No pudimos comunicarnos con el bot.');
        expect(block.textContent).not.toMatch(/network_error|command_version/);
        expect(within(block).queryByRole('button', { name: 'Reintentar reanudar bot' })).not.toBeInTheDocument();

        fireEvent.click(within(block).getByRole('button', { name: 'Reintentar tomar conversación' }));
        await confirmInDialog('¿Tomar esta conversación?', 'Tomar conversación');
        await waitFor(() => expect(leadsApi.takeoverLead).toHaveBeenCalledTimes(1));
        expect(leadsApi.releaseLead).not.toHaveBeenCalled();
    });

    it('error de release: Reintentar reanudar bot según last_action (aunque haya taken_at)', async () => {
        leadsApi.getLead.mockResolvedValue(
            withControl({ ...TAKEN, state: 'error', command_version: 2, last_action: 'release', last_error_code: 'version_regression' }),
        );
        leadsApi.releaseLead.mockResolvedValue({ ok: true, state: 'release_pending', command_version: 3 });
        renderClient();

        const block = await screen.findByTestId('lead-conversation-control');
        expect(within(block).getByRole('alert')).toHaveTextContent('El estado de la conversación está desincronizado.');
        expect(within(block).queryByRole('button', { name: 'Reintentar tomar conversación' })).not.toBeInTheDocument();
        fireEvent.click(within(block).getByRole('button', { name: 'Reintentar reanudar bot' }));
        await confirmInDialog('¿Reanudar el bot?', 'Reanudar bot');
        await waitFor(() => expect(leadsApi.releaseLead).toHaveBeenCalledTimes(1));
        expect(leadsApi.takeoverLead).not.toHaveBeenCalled();
    });

    it('error con código desconocido usa el texto genérico', async () => {
        leadsApi.getLead.mockResolvedValue(withControl({ state: 'error', command_version: 1, last_action: 'takeover', last_error_code: 'http_502' }));
        renderClient();
        const block = await screen.findByTestId('lead-conversation-control');
        expect(within(block).getByRole('alert')).toHaveTextContent('No pudimos cambiar el control de esta conversación.');
        expect(block.textContent).not.toMatch(/http_502/);
    });

    it('available=false: sin botones mutables, explicación discreta y WhatsApp intacto', async () => {
        leadsApi.getLead.mockResolvedValue(withControl({ available: false }));
        renderClient();
        const block = await screen.findByTestId('lead-conversation-control');
        expect(
            within(block).getByText(
                'El bot está habilitado para este paciente (este estado no confirma que sus mensajes se estén entregando: revisá el historial de la conversación). Pausarlo o retomarlo manualmente desde acá no está disponible: el control manual no está habilitado para este canal.',
            ),
        ).toBeInTheDocument();
        expect(within(block).queryAllByRole('button')).toHaveLength(0);
        expect(within(block).queryByRole('alert')).not.toBeInTheDocument();
        expect(within(block).getByRole('link', { name: 'Abrir WhatsApp' })).toBeInTheDocument();
    });

    it('solo lectura (view_leads): ve el estado pero no puede accionar', async () => {
        const cases: Array<[LeadConversationControl, string]> = [
            [control(TAKEN), 'Conversación tomada'],
            [control({ state: 'takeover_pending', command_version: 1, last_action: 'takeover' }), 'Procesando'],
            [control({ state: 'active' }), 'Bot habilitado'],
        ];
        for (const [ctl, label] of cases) {
            leadsApi.getLead.mockResolvedValue(leadDetail({ conversation_control: ctl }));
            queryClient.clear();
            const view = renderClient({ canManage: false });
            const block = await screen.findByTestId('lead-conversation-control');
            expect(within(block).getByText(label)).toBeInTheDocument();
            expect(within(block).queryAllByRole('button')).toHaveLength(0);
            view.unmount();
        }
    });

    it('409 (acción opuesta en curso): refresca, avisa sin error genérico y muestra el estado real', async () => {
        leadsApi.getLead
            .mockResolvedValueOnce(withControl())
            .mockResolvedValue(withControl({ ...TAKEN, state: 'release_pending', command_version: 2, last_action: 'release' }));
        leadsApi.takeoverLead.mockRejectedValue(
            new ApiError('Conflict', 409, { ok: false, code: 'command_in_progress', detail: 'Hay otra acción en curso.' }),
        );
        renderClient();

        fireEvent.click(await screen.findByRole('button', { name: 'Tomar conversación' }));
        await confirmInDialog('¿Tomar esta conversación?', 'Tomar conversación');

        expect(await screen.findByText('El estado de la conversación cambió. Actualizamos la información.')).toBeInTheDocument();
        expect(await screen.findByRole('button', { name: 'Reanudando bot…' })).toBeDisabled();
        expect(screen.queryByText(/No pudimos cambiar el control/)).not.toBeInTheDocument();
        expect(screen.queryByText('Hay otra acción en curso.')).not.toBeInTheDocument();
        expect(screen.queryByRole('alert')).not.toBeInTheDocument();
        expect(leadsApi.takeoverLead).toHaveBeenCalledTimes(1);
    });

    it('dos navegadores: takeover idempotente (200 ya tomada) muestra el estado real sin error', async () => {
        leadsApi.getLead.mockResolvedValueOnce(withControl()).mockResolvedValue(withControl(TAKEN));
        leadsApi.takeoverLead.mockResolvedValue({ ok: true, state: 'taken', command_version: 1 });
        renderClient();

        fireEvent.click(await screen.findByRole('button', { name: 'Tomar conversación' }));
        await confirmInDialog('¿Tomar esta conversación?', 'Tomar conversación');

        expect(await screen.findByText('Conversación tomada')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Reanudar bot' })).toBeEnabled();
        expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });

    it('503 (integración apagada): aviso claro, refetch y sin loading infinito', async () => {
        leadsApi.getLead.mockResolvedValue(withControl());
        leadsApi.takeoverLead.mockRejectedValue(new ApiError('Unavailable', 503, { ok: false, code: 'takeover_disabled' }));
        renderClient();

        fireEvent.click(await screen.findByRole('button', { name: 'Tomar conversación' }));
        await confirmInDialog('¿Tomar esta conversación?', 'Tomar conversación');

        expect(await screen.findByText('El control del bot no está disponible en este momento.')).toBeInTheDocument();
        await waitFor(() => expect(leadsApi.getLead).toHaveBeenCalledTimes(2));
        expect(screen.getByRole('button', { name: 'Tomar conversación' })).toBeEnabled();
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('sin retry del frontend aunque el QueryClient tenga retries por defecto', async () => {
        queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: 3, retryDelay: 0 } } });
        leadsApi.getLead.mockResolvedValue(withControl());
        leadsApi.takeoverLead.mockRejectedValue(new ApiError('Server error', 500, {}));
        renderClient();

        fireEvent.click(await screen.findByRole('button', { name: 'Tomar conversación' }));
        await confirmInDialog('¿Tomar esta conversación?', 'Tomar conversación');

        expect(await screen.findByText('No pudimos cambiar el control de esta conversación. Intentá nuevamente.')).toBeInTheDocument();
        expect(leadsApi.takeoverLead).toHaveBeenCalledTimes(1);
    });
});

describe('historial de la conversación (LEADS 05C)', () => {
    function msg(overrides: Partial<LeadMessage>): LeadMessage {
        return {
            id: `msg-${Math.random()}`,
            role: 'user',
            sender: 'patient',
            text: 'hola',
            sent_at: '2026-10-05T13:00:00Z',
            status: null,
            authored_by: null,
            ...overrides,
        };
    }

    it('paciente a la izquierda con su número, bot a la derecha, en orden cronológico', async () => {
        leadsApi.listLeadMessages.mockResolvedValue(
            messagesPage([
                msg({ id: 'm1', role: 'user', sender: 'patient', text: 'hola, dolor de muela', sent_at: '2026-10-05T13:00:00Z' }),
                msg({ id: 'm2', role: 'assistant', sender: 'bot', text: 'contame más', sent_at: '2026-10-05T13:01:00Z', status: 'delivered' }),
            ]),
        );
        renderClient();

        const scroll = await screen.findByTestId('lead-conversation-scroll');
        const bubbles = within(scroll).getAllByTestId('lead-message-bubble');
        expect(bubbles).toHaveLength(2);
        expect(bubbles[0]).toHaveAttribute('data-role', 'user');
        expect(within(bubbles[0]).getByText(/Paciente/)).toBeInTheDocument();
        expect(within(bubbles[0]).getByText(/\+5491155550101/)).toBeInTheDocument();
        expect(within(bubbles[0]).getByText('hola, dolor de muela')).toBeInTheDocument();
        expect(bubbles[1]).toHaveAttribute('data-role', 'assistant');
        expect(within(bubbles[1]).getByText('Bot')).toBeInTheDocument();
        expect(within(bubbles[1]).getByText('contame más')).toBeInTheDocument();
        expect(within(bubbles[1]).getByText('Entregado')).toBeInTheDocument();
    });

    it('separa los mensajes de distintos días', async () => {
        leadsApi.listLeadMessages.mockResolvedValue(
            messagesPage([
                msg({ id: 'm1', sent_at: '2026-10-04T13:00:00Z' }),
                msg({ id: 'm2', sent_at: '2026-10-05T13:00:00Z' }),
            ]),
        );
        renderClient();

        const scroll = await screen.findByTestId('lead-conversation-scroll');
        await waitFor(() => expect(within(scroll).getAllByTestId('lead-message-bubble')).toHaveLength(2));
        // Dos bloques de día distintos: dos textos de fecha ("domingo" no aplica, usa dd/mm/yyyy fuera de hoy/ayer).
        expect(within(scroll).getByText('04/10/2026')).toBeInTheDocument();
        expect(within(scroll).getByText('05/10/2026')).toBeInTheDocument();
    });

    it('sin historial: lo dice explícitamente (nunca inventa mensajes)', async () => {
        leadsApi.listLeadMessages.mockResolvedValue(messagesPage([]));
        renderClient();
        expect(await screen.findByText('No hay historial de mensajes anterior para este lead.')).toBeInTheDocument();
        expect(screen.queryByTestId('lead-message-bubble')).not.toBeInTheDocument();
    });

    it('un mensaje fallido muestra el estado de fallo', async () => {
        leadsApi.listLeadMessages.mockResolvedValue(
            messagesPage([msg({ id: 'm1', role: 'assistant', sender: 'bot', text: 'no se pudo', status: 'failed' })]),
        );
        renderClient();
        const scroll = await screen.findByTestId('lead-conversation-scroll');
        expect(within(scroll).getByText('No enviado')).toBeInTheDocument();
    });

    it('un mensaje saliente sin evidencia de Meta muestra estado desconocido, nunca "enviado"', async () => {
        leadsApi.listLeadMessages.mockResolvedValue(
            messagesPage([msg({ id: 'm1', role: 'assistant', sender: 'bot', text: 'sin confirmar', status: null })]),
        );
        renderClient();
        const scroll = await screen.findByTestId('lead-conversation-scroll');
        expect(within(scroll).getByText('Estado desconocido')).toBeInTheDocument();
        expect(within(scroll).queryByText('Enviado')).not.toBeInTheDocument();
    });

    it('un mensaje de recepción (staff) se identifica distinto del bot', async () => {
        leadsApi.listLeadMessages.mockResolvedValue(
            messagesPage([msg({ id: 'm1', role: 'assistant', sender: 'staff', text: 'te escribo yo', status: 'sent' })]),
        );
        renderClient();
        const scroll = await screen.findByTestId('lead-conversation-scroll');
        expect(within(scroll).getByText('Recepción')).toBeInTheDocument();
    });

    it('un mensaje de staff con authored_by muestra el nombre de quien lo escribió', async () => {
        leadsApi.listLeadMessages.mockResolvedValue(
            messagesPage([
                msg({
                    id: 'm1', role: 'assistant', sender: 'staff', text: 'te escribo yo', status: 'sent',
                    authored_by: { id: 3, display_name: 'Bea Paz' },
                }),
            ]),
        );
        renderClient();
        const scroll = await screen.findByTestId('lead-conversation-scroll');
        expect(within(scroll).getByText('Bea Paz')).toBeInTheDocument();
        expect(within(scroll).queryByText('Recepción')).not.toBeInTheDocument();
    });

    it('actualiza con mensajes nuevos sin recargar todo el historial (poll incremental)', async () => {
        vi.useFakeTimers();
        try {
            leadsApi.listLeadMessages
                .mockResolvedValueOnce(messagesPage([msg({ id: 'm1', sent_at: '2026-10-05T13:00:00Z' })]))
                .mockResolvedValueOnce(
                    messagesPage([msg({ id: 'm2', role: 'assistant', sender: 'bot', text: 'nuevo', sent_at: '2026-10-05T13:05:00Z' })]),
                );
            renderClient();

            await vi.waitFor(() => expect(screen.getByTestId('lead-conversation-scroll')).toBeInTheDocument());
            await vi.advanceTimersByTimeAsync(8100);
            await vi.waitFor(() => expect(screen.getAllByTestId('lead-message-bubble')).toHaveLength(2));

            expect(leadsApi.listLeadMessages).toHaveBeenLastCalledWith('lead-1', {
                since: '2026-10-05T13:00:00Z',
                limit: 500,
            });
            // El primer mensaje sigue ahí: no se volvió a pedir ni redibujar todo.
            expect(screen.getByText('hola')).toBeInTheDocument();
            expect(screen.getByText('nuevo')).toBeInTheDocument();
        } finally {
            vi.useRealTimers();
        }
    });
});

describe('responder desde el chat (MIRUBRO HUMAN MESSAGES)', () => {
    beforeEach(() => {
        leadsApi.listLeadMessages.mockResolvedValue(messagesPage([]));
    });

    it('oculto sin conversation_control (lead sin conversación del agente)', async () => {
        renderClient();
        await screen.findByRole('heading', { name: 'Ana Pérez' });
        expect(screen.queryByRole('textbox', { name: 'Mensaje para el paciente' })).not.toBeInTheDocument();
    });

    it('oculto cuando el control no está en "taken" (active/pending/error)', async () => {
        for (const state of ['active', 'takeover_pending', 'release_pending', 'error'] as const) {
            leadsApi.getLead.mockResolvedValue(withControl({ state, last_action: state === 'error' ? 'takeover' : null }));
            const view = renderClient();
            await screen.findByTestId('lead-conversation-control');
            expect(screen.queryByRole('textbox', { name: 'Mensaje para el paciente' })).not.toBeInTheDocument();
            view.unmount();
        }
    });

    it('oculto sin manage_leads aunque la conversación esté tomada', async () => {
        leadsApi.getLead.mockResolvedValue(withControl(TAKEN));
        renderClient({ canManage: false });
        await screen.findByTestId('lead-conversation-control');
        expect(screen.queryByRole('textbox', { name: 'Mensaje para el paciente' })).not.toBeInTheDocument();
    });

    it('visible cuando está tomada y hay manage_leads: envía y limpia el textarea', async () => {
        leadsApi.getLead.mockResolvedValue(withControl(TAKEN));
        leadsApi.sendLeadMessage.mockResolvedValue({ ok: true, status: 'queued_locally', id: 'msg-1' });
        renderClient();

        const textarea = await screen.findByRole('textbox', { name: 'Mensaje para el paciente' });
        fireEvent.change(textarea, { target: { value: 'Hola, ¿cómo estás?' } });
        fireEvent.click(screen.getByRole('button', { name: 'Enviar' }));

        await waitFor(() => expect(leadsApi.sendLeadMessage).toHaveBeenCalledWith('lead-1', 'Hola, ¿cómo estás?'));
        await waitFor(() => expect(textarea).toHaveValue(''));
        // Nunca dice "enviado": solo se limpia el campo, el estado real lo muestra el historial.
        expect(screen.queryByText(/enviado/i)).not.toBeInTheDocument();
    });

    it('botón deshabilitado con texto vacío o solo espacios (sin llamar a la API)', async () => {
        leadsApi.getLead.mockResolvedValue(withControl(TAKEN));
        renderClient();
        const textarea = await screen.findByRole('textbox', { name: 'Mensaje para el paciente' });
        const button = screen.getByRole('button', { name: 'Enviar' });
        expect(button).toBeDisabled();
        fireEvent.change(textarea, { target: { value: '   ' } });
        expect(button).toBeDisabled();
        fireEvent.click(button);
        expect(leadsApi.sendLeadMessage).not.toHaveBeenCalled();
    });

    it('botón deshabilitado por encima del límite de caracteres', async () => {
        leadsApi.getLead.mockResolvedValue(withControl(TAKEN));
        renderClient();
        const textarea = await screen.findByRole('textbox', { name: 'Mensaje para el paciente' });
        fireEvent.change(textarea, { target: { value: 'a'.repeat(4097) } });
        expect(screen.getByRole('button', { name: 'Enviar' })).toBeDisabled();
        expect(leadsApi.sendLeadMessage).not.toHaveBeenCalled();
    });

    it('mientras envía: deshabilita el textarea y el botón (sin doble envío)', async () => {
        let resolveSend: (value: { ok: true; status: 'queued_locally'; id: string }) => void = () => { };
        leadsApi.getLead.mockResolvedValue(withControl(TAKEN));
        leadsApi.sendLeadMessage.mockReturnValue(new Promise((resolve) => { resolveSend = resolve; }));
        renderClient();

        const textarea = await screen.findByRole('textbox', { name: 'Mensaje para el paciente' });
        fireEvent.change(textarea, { target: { value: 'Hola' } });
        fireEvent.click(screen.getByRole('button', { name: 'Enviar' }));

        expect(await screen.findByRole('button', { name: 'Enviando…' })).toBeDisabled();
        expect(textarea).toBeDisabled();
        fireEvent.click(screen.getByRole('button', { name: 'Enviando…' }));
        expect(leadsApi.sendLeadMessage).toHaveBeenCalledTimes(1);

        resolveSend({ ok: true, status: 'queued_locally', id: 'msg-1' });
        // Termina el envío: vuelve a "Enviar" y se reactiva el textarea. El botón
        // sigue deshabilitado porque el texto se limpió (mismo criterio que el
        // test de "texto vacío" de arriba), no porque siga enviando.
        await waitFor(() => expect(screen.getByRole('button', { name: 'Enviar' })).toBeInTheDocument());
        expect(textarea).toBeEnabled();
        expect(screen.getByRole('button', { name: 'Enviar' })).toBeDisabled();
    });

    it('error del backend: muestra el mensaje específico y conserva el texto escrito', async () => {
        leadsApi.getLead.mockResolvedValue(withControl(TAKEN));
        leadsApi.sendLeadMessage.mockRejectedValue(new ApiError('Forbidden', 403, { detail: 'No tenés permiso.' }));
        renderClient();

        const textarea = await screen.findByRole('textbox', { name: 'Mensaje para el paciente' });
        fireEvent.change(textarea, { target: { value: 'Hola' } });
        fireEvent.click(screen.getByRole('button', { name: 'Enviar' }));

        expect(await screen.findByRole('alert')).toHaveTextContent('No tenés permiso para enviar mensajes en este lead.');
        expect(textarea).toHaveValue('Hola'); // no se pierde lo escrito ante un error
    });

    it('error 503 (envío deshabilitado) usa un mensaje claro', async () => {
        leadsApi.getLead.mockResolvedValue(withControl(TAKEN));
        leadsApi.sendLeadMessage.mockRejectedValue(new ApiError('Unavailable', 503, { code: 'takeover_disabled' }));
        renderClient();

        const textarea = await screen.findByRole('textbox', { name: 'Mensaje para el paciente' });
        fireEvent.change(textarea, { target: { value: 'Hola' } });
        fireEvent.click(screen.getByRole('button', { name: 'Enviar' }));

        expect(await screen.findByRole('alert')).toHaveTextContent('El envío de mensajes no está habilitado en este momento.');
    });
});
