import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { AnchorHTMLAttributes } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// LEADS 05A: bandeja `/app/turnos/leads`. Gating (flag `leads` + `view_leads`),
// render, estados, filtros server-side, búsqueda, paginación y navegación.

const navigation = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({ redirect: vi.fn(), useRouter: () => navigation }));

vi.mock('next/link', () => ({
    __esModule: true,
    default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
        <a href={href} {...props}>{children}</a>
    ),
}));

vi.mock('@/lib/auth', () => ({ getSession: vi.fn() }));

const hooks = vi.hoisted(() => ({ useLeads: vi.fn() }));
vi.mock('@/features/leads/hooks', () => hooks);

import { ApiError } from '@/lib/api/client';
import { getSession } from '@/lib/auth';
import type { LeadFilters, LeadListAppointment, LeadListItem } from '@/features/leads/types';

import LeadsPage from '../page';
import LeadDetailPage from '../[id]/page';
import { LEADS_PAGE_SIZE, LeadsInboxClient, resolveLeadCta, type LeadCtaContext } from '../leads-inbox-client';

const getSessionMock = vi.mocked(getSession);
const TZ = 'America/Argentina/Buenos_Aires';

function session({ features = {}, permissions = {} }: { features?: Record<string, boolean>; permissions?: Record<string, boolean> }) {
    return {
        user: { id: 7, email: 'ana@example.com', name: 'Ana' },
        features: { appointments_core: true, leads: true, ...features },
        permissions: { view_leads: true, ...permissions },
        services: { enabled: ['appointments'] },
        current: { business: { id: 1, name: 'Turnos', status: 'active', timezone: TZ }, role: 'manager', service: 'appointments' },
    } as any;
}

function lead(overrides: Partial<LeadListItem> = {}, agent: Partial<NonNullable<LeadListItem['agent']>> = {}): LeadListItem {
    return {
        id: 'lead-1',
        source: 'whatsapp_agent',
        status: 'new',
        outcome: null,
        // 05/10/2026 13:00 UTC = 10:00 en Buenos Aires.
        created_at: '2026-10-05T13:00:00Z',
        updated_at: '2026-10-05T13:00:00Z',
        needs_attention_at: null,
        needs_attention: false,
        acknowledged_at: null,
        assigned_to: null,
        customer: null,
        conversation_state: 'active',
        conversation_control: null,
        appointment: null,
        last_patient_message_text: null,
        last_patient_message_at: null,
        agent: {
            patient_name: 'Ana Pérez',
            whatsapp_profile_name: 'Anita',
            phone_e164: '+5491155550101',
            reason: 'Quiere un turno para corte',
            preferred_time: 'mañana',
            urgency: false,
            agent_status: 'active',
            handoff_requested: false,
            handoff_reasons: [],
            summary: 'Resumen del agente',
            last_message_at: '2026-10-05T14:30:00Z',
            ...agent,
        },
        ...overrides,
    };
}

function mockLeads(results: LeadListItem[], extra: Record<string, unknown> = {}) {
    hooks.useLeads.mockReturnValue({
        data: { count: results.length, next: null, previous: null, results },
        isLoading: false,
        isError: false,
        isFetching: false,
        error: null,
        refetch: vi.fn(),
        ...extra,
    });
}

function lastFilters(): LeadFilters {
    const calls = hooks.useLeads.mock.calls;
    return calls[calls.length - 1][0];
}

function renderInbox(props: Partial<Parameters<typeof LeadsInboxClient>[0]> = {}) {
    return render(<LeadsInboxClient currentUserId={7} businessTimeZone={TZ} {...props} />);
}

function openMoreFilters() {
    fireEvent.click(screen.getByRole('button', { name: /Más filtros/ }));
}

function appointment(overrides: Partial<LeadListAppointment> = {}): LeadListAppointment {
    return {
        id: 'appt-1',
        status: 'confirmed',
        // 26/10/2026 18:30 UTC = 15:30 en Buenos Aires.
        start_at: '2026-10-26T18:30:00Z',
        end_at: '2026-10-26T19:00:00Z',
        service_name: 'Limpieza',
        professional_name: 'Dra. X',
        is_upcoming: true,
        is_past: false,
        ...overrides,
    };
}

const ALL_PERMS: LeadCtaContext = { canManage: true, canManageAppointments: true, canViewAppointments: true, timeZone: TZ };

beforeEach(() => {
    vi.clearAllMocks();
    mockLeads([lead()]);
});

describe('gating de la página', () => {
    it('carga la bandeja con el flag `leads` y `view_leads`', async () => {
        getSessionMock.mockResolvedValue(session({}));
        render(await LeadsPage());
        expect(screen.getByRole('heading', { name: 'Leads' })).toBeInTheDocument();
        expect(screen.getByText('Ana Pérez')).toBeInTheDocument();
    });

    it('sin el entitlement (flag `leads`) muestra el aviso de plan y no consulta la API', async () => {
        getSessionMock.mockResolvedValue(session({ features: { leads: false } }));
        render(await LeadsPage());
        expect(screen.getByText('Tu plan no incluye Leads')).toBeInTheDocument();
        expect(hooks.useLeads).not.toHaveBeenCalled();
    });

    it('sin `view_leads` muestra Sin acceso y no consulta la API', async () => {
        getSessionMock.mockResolvedValue(session({ permissions: { view_leads: false } }));
        render(await LeadsPage());
        expect(screen.getByText('Sin acceso')).toBeInTheDocument();
        expect(hooks.useLeads).not.toHaveBeenCalled();
    });

    it('la ruta de detalle aplica el mismo gating', async () => {
        getSessionMock.mockResolvedValue(session({ permissions: { view_leads: false } }));
        render(await LeadDetailPage({ params: Promise.resolve({ id: 'lead-1' }) }));
        expect(screen.getByText('Sin acceso')).toBeInTheDocument();

        getSessionMock.mockResolvedValue(session({ features: { leads: false } }));
        render(await LeadDetailPage({ params: Promise.resolve({ id: 'lead-1' }) }));
        expect(screen.getByText('Tu plan no incluye Leads')).toBeInTheDocument();

        // Con acceso entrega el detalle operativo (LEADS 05B, cubierto en lead-detail.test.tsx).
        getSessionMock.mockResolvedValue(session({}));
        const element = await LeadDetailPage({ params: Promise.resolve({ id: 'lead-1' }) });
        expect(element.props).toMatchObject({ leadId: 'lead-1', canManage: false });
    });
});

describe('listado', () => {
    it('muestra los datos de cada lead sin payload técnico del agente', () => {
        mockLeads([
            lead({
                assigned_to: { id: 3, display_name: 'Bea Paz' },
                customer: { id: 'c-1', display_name: 'Ana Cliente' },
            }),
        ]);
        renderInbox();
        const row = screen.getByTestId('lead-row');
        expect(within(row).getByText('Ana Pérez')).toBeInTheDocument();
        expect(within(row).getByText(/\+5491155550101/)).toBeInTheDocument();
        expect(within(row).getByText(/Agente de WhatsApp/)).toBeInTheDocument();
        expect(within(row).getByTestId('lead-intent')).toHaveTextContent('Quiere un turno para corte · Prefiere mañana');
        expect(within(row).getByText('Nuevo')).toBeInTheDocument();
        expect(within(row).getByText('Asignado a Bea Paz')).toBeInTheDocument();
        expect(within(row).getByText(/Cliente: Ana Cliente/)).toBeInTheDocument();
        // Horas en la zona del Business.
        expect(within(row).getByText('05/10/2026 11:30')).toBeInTheDocument();
        expect(within(row).getByText('05/10/2026 10:00')).toBeInTheDocument();
        expect(screen.getByText('1 lead')).toBeInTheDocument();
        expect(row.textContent).not.toMatch(/applied_version|payload_hash|handoff_reasons/);
    });

    it('cae al nombre de WhatsApp, cliente o teléfono y usa el resumen si no hay motivo', () => {
        mockLeads([
            lead({ id: 'a' }, { patient_name: null, reason: null }),
            lead({ id: 'b', customer: { id: 'c', display_name: 'Cliente X' } }, { patient_name: null, whatsapp_profile_name: null }),
            lead({ id: 'c' }, { patient_name: null, whatsapp_profile_name: null }),
        ]);
        renderInbox();
        const rows = screen.getAllByTestId('lead-row');
        expect(within(rows[0]).getByText('Anita')).toBeInTheDocument();
        expect(within(rows[0]).getByTestId('lead-intent')).toHaveTextContent('Resumen del agente');
        expect(within(rows[1]).getByText('Cliente X')).toBeInTheDocument();
        expect(within(rows[2]).getAllByText('+5491155550101')).toHaveLength(1);
    });

    it('distingue atención pendiente, urgente, sin asignar y cerrado usando lo que manda el backend', () => {
        mockLeads([
            lead({ id: 'pending', needs_attention: true, needs_attention_at: '2026-10-05T13:10:00Z' }, { urgency: true }),
            // `needs_attention_at` histórico pero ya reconocido: el backend dice false.
            lead({ id: 'acked', needs_attention: false, needs_attention_at: '2026-10-05T13:10:00Z', acknowledged_at: '2026-10-05T13:20:00Z' }),
            lead({ id: 'closed', status: 'closed', outcome: 'booked' }),
        ]);
        renderInbox();
        const [pending, acked, closed] = screen.getAllByTestId('lead-row');
        expect(within(pending).getByText('Necesita revisión')).toBeInTheDocument();
        expect(pending).toHaveAttribute('data-attention', 'pending');
        expect(within(pending).getByText('Urgente')).toBeInTheDocument();
        expect(within(pending).getByText('Sin asignar')).toBeInTheDocument();
        expect(within(acked).queryByText('Necesita revisión')).not.toBeInTheDocument();
        expect(acked).not.toHaveAttribute('data-attention');
        expect(within(acked).queryByText('Urgente')).not.toBeInTheDocument();
        expect(within(closed).getByText('Cerrado · Turno agendado')).toBeInTheDocument();
    });

    it('respeta el orden del backend (no reordena)', () => {
        mockLeads([
            lead({ id: 'z', created_at: '2026-10-01T10:00:00Z' }, { patient_name: 'Primero' }),
            lead({ id: 'a', created_at: '2026-10-05T10:00:00Z', needs_attention: false }, { patient_name: 'Segundo' }),
        ]);
        renderInbox();
        const names = screen.getAllByTestId('lead-name').map((link) => link.textContent);
        expect(names).toEqual(['Primero', 'Segundo']);
    });

    it('el nombre navega al detalle sin anchors anidados', () => {
        renderInbox();
        const row = screen.getByTestId('lead-row');
        expect(row.tagName).toBe('LI');
        expect(within(row).getByTestId('lead-name')).toHaveAttribute('href', '/app/turnos/leads/lead-1');
        expect(row.querySelector('a a, a button, button a')).toBeNull();
    });

    it('click en el cuerpo abre el detalle una sola vez', () => {
        renderInbox();
        const row = screen.getByTestId('lead-row');
        fireEvent.click(within(row).getByTestId('lead-intent'));
        expect(navigation.push).toHaveBeenCalledExactlyOnceWith('/app/turnos/leads/lead-1');
        expect(within(row).getByTestId('lead-name')).toHaveAttribute('href', '/app/turnos/leads/lead-1');
    });

    it.each(['{Enter}', ' '])('%s en la card abre el detalle', async (key) => {
        const user = userEvent.setup();
        renderInbox();
        const link = screen.getByTestId('lead-name');
        const activated = vi.fn((event: Event) => event.preventDefault());
        link.addEventListener('click', activated);
        link.focus();
        expect(link).toHaveFocus();
        await user.keyboard(key);
        expect(activated).toHaveBeenCalledTimes(1);
        expect(link).toHaveAttribute('href', '/app/turnos/leads/lead-1');
        expect(navigation.push).not.toHaveBeenCalled();
    });

    it('CTA y nombre conservan su destino sin navegación general adicional', () => {
        mockLeads([lead({ appointment: appointment() })]);
        renderInbox({ canViewAppointments: true });
        const cta = screen.getByTestId('lead-cta');
        expect(cta).toHaveAttribute('href', '/app/turnos/turnos?date=2026-10-26&appointment=appt-1');
        cta.focus();
        expect(cta).toHaveFocus();
        fireEvent.keyDown(cta, { key: 'Enter' });
        fireEvent.keyDown(cta, { key: ' ' });
        fireEvent.click(cta);
        fireEvent.click(screen.getByTestId('lead-name'));
        expect(navigation.push).not.toHaveBeenCalled();
        expect(screen.getByTestId('lead-row').querySelector('a a, a button, button a')).toBeNull();
    });
});

describe('estados', () => {
    it('loading', () => {
        hooks.useLeads.mockReturnValue({ data: undefined, isLoading: true, isError: false, isFetching: true, refetch: vi.fn() });
        renderInbox();
        expect(screen.getByRole('status')).toHaveTextContent('Cargando leads…');
    });

    it('vacío sin filtros y vacío con filtros', () => {
        mockLeads([]);
        renderInbox();
        expect(screen.getByText('Todavía no llegaron consultas del agente de WhatsApp.')).toBeInTheDocument();

        openMoreFilters();
        fireEvent.change(screen.getByLabelText('Estado'), { target: { value: 'closed' } });
        expect(screen.getByText('No hay leads que coincidan con los filtros.')).toBeInTheDocument();
    });

    it('error con reintento', () => {
        const refetch = vi.fn();
        hooks.useLeads.mockReturnValue({
            data: undefined, isLoading: false, isError: true, isFetching: false, refetch, error: new ApiError('boom', 500),
        });
        renderInbox();
        expect(screen.getByRole('alert')).toHaveTextContent('No pudimos cargar los leads.');
        fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }));
        expect(refetch).toHaveBeenCalled();
    });

    it('error 403 por entitlement muestra el aviso de plan', () => {
        hooks.useLeads.mockReturnValue({
            data: undefined, isLoading: false, isError: true, isFetching: false, refetch: vi.fn(),
            error: new ApiError('x', 403, { code: 'plan_entitlement_required' }),
        });
        renderInbox();
        expect(screen.getByRole('alert')).toHaveTextContent('Tu plan no incluye la bandeja de Leads.');
    });

    it('Actualizar vuelve a consultar', () => {
        const refetch = vi.fn();
        mockLeads([lead()], { refetch });
        renderInbox();
        fireEvent.click(screen.getByRole('button', { name: 'Actualizar' }));
        expect(refetch).toHaveBeenCalled();
    });
});

describe('filtros y búsqueda (server-side)', () => {
    it('por defecto pide la primera página sin filtros ni ordering', () => {
        renderInbox();
        expect(lastFilters()).toEqual({
            status: undefined, source: undefined, outcome: undefined, urgency: undefined, needsAttention: undefined,
            assignedTo: undefined, customer: undefined, appointment: undefined, q: undefined, limit: LEADS_PAGE_SIZE, offset: 0,
        });
    });

    it('filtros principales visibles; Estado/Urgencia/Cliente/Resultado en "Más filtros"; sin Canal', () => {
        renderInbox();
        expect(screen.getByLabelText('Atención')).toBeInTheDocument();
        expect(screen.getByLabelText('Turno')).toBeInTheDocument();
        expect(screen.getByLabelText('Asignación')).toBeInTheDocument();
        expect(screen.queryByLabelText('Estado')).not.toBeInTheDocument();
        expect(screen.queryByLabelText('Canal')).not.toBeInTheDocument();

        const toggle = screen.getByRole('button', { name: 'Más filtros' });
        expect(toggle).toHaveAttribute('aria-expanded', 'false');
        fireEvent.click(toggle);
        expect(screen.getByRole('button', { name: 'Menos filtros' })).toHaveAttribute('aria-expanded', 'true');
        for (const label of ['Estado', 'Urgencia', 'Cliente', 'Resultado']) {
            expect(screen.getByLabelText(label)).toBeInTheDocument();
        }
        expect(screen.queryByLabelText('Canal')).not.toBeInTheDocument();

        // Un filtro secundario activo se ve aunque el panel esté cerrado.
        fireEvent.change(screen.getByLabelText('Urgencia'), { target: { value: 'true' } });
        fireEvent.click(screen.getByRole('button', { name: /^Menos filtros/ }));
        expect(screen.getByRole('button', { name: 'Más filtros (1)' })).toBeInTheDocument();
        expect(lastFilters().urgency).toBe(true);
    });

    it('Con/Sin turno se envía como `appointment=with|without`', () => {
        renderInbox();
        fireEvent.change(screen.getByLabelText('Turno'), { target: { value: 'with' } });
        expect(lastFilters()).toMatchObject({ appointment: 'with', offset: 0 });
        fireEvent.change(screen.getByLabelText('Turno'), { target: { value: 'without' } });
        expect(lastFilters().appointment).toBe('without');
        fireEvent.change(screen.getByLabelText('Turno'), { target: { value: '' } });
        expect(lastFilters().appointment).toBeUndefined();
    });

    it('cada filtro se traduce al parámetro de la API', () => {
        renderInbox();
        openMoreFilters();
        fireEvent.change(screen.getByLabelText('Atención'), { target: { value: 'true' } });
        fireEvent.change(screen.getByLabelText('Urgencia'), { target: { value: 'false' } });
        fireEvent.change(screen.getByLabelText('Estado'), { target: { value: 'closed' } });
        fireEvent.change(screen.getByLabelText('Resultado'), { target: { value: 'spam' } });
        fireEvent.change(screen.getByLabelText('Cliente'), { target: { value: 'unlinked' } });
        fireEvent.change(screen.getByLabelText('Asignación'), { target: { value: 'unassigned' } });
        expect(lastFilters()).toMatchObject({
            needsAttention: true, urgency: false, status: 'closed', outcome: 'spam',
            customer: 'unlinked', assignedTo: 'unassigned', offset: 0,
        });
        expect(lastFilters().source).toBeUndefined();

        fireEvent.change(screen.getByLabelText('Asignación'), { target: { value: 'me' } });
        expect(lastFilters().assignedTo).toBe('7');

        fireEvent.click(screen.getByRole('button', { name: 'Limpiar filtros' }));
        expect(lastFilters()).toMatchObject({ needsAttention: undefined, status: undefined, assignedTo: undefined });
    });

    it('la búsqueda se envía como `q` (con debounce) y vuelve a la primera página', async () => {
        mockLeads([lead()], { data: { count: 60, next: 'x', previous: null, results: [lead()] } });
        renderInbox();
        fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }));
        expect(lastFilters().offset).toBe(LEADS_PAGE_SIZE);

        fireEvent.change(screen.getByLabelText('Buscar leads'), { target: { value: '  11 5555  ' } });
        await waitFor(() => expect(lastFilters().q).toBe('11 5555'));
        expect(lastFilters().offset).toBe(0);
    });
});

describe('paginación', () => {
    it('navega páginas con limit/offset y oculta la paginación si entra en una página', () => {
        hooks.useLeads.mockReturnValue({
            data: { count: 60, next: 'x', previous: null, results: [lead()] },
            isLoading: false, isError: false, isFetching: false, refetch: vi.fn(),
        });
        renderInbox();
        expect(screen.getByText('Página 1 de 3')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Anterior' })).toBeDisabled();

        fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }));
        expect(lastFilters().offset).toBe(25);
        expect(screen.getByText('Página 2 de 3')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }));
        expect(lastFilters().offset).toBe(50);
        expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled();

        // Cambiar un filtro vuelve a la primera página.
        openMoreFilters();
        fireEvent.change(screen.getByLabelText('Estado'), { target: { value: 'new' } });
        expect(lastFilters().offset).toBe(0);
    });

    it('sin paginación cuando todo entra en una página', () => {
        renderInbox();
        expect(screen.queryByRole('navigation', { name: 'Paginación' })).not.toBeInTheDocument();
    });
});

describe('control de la conversación (TAKEOVER 05B)', () => {
    it('muestra quién tomó la conversación (no el asignado) y estados pendientes/error; active sin ruido', () => {
        mockLeads([
            lead({
                id: 'taken',
                conversation_state: 'taken',
                assigned_to: { id: 3, display_name: 'Bea Paz' },
                conversation_control: { state: 'taken', taken_by: { id: 9, display_name: 'QA Owner' }, taken_at: '2026-10-05T14:00:00Z' },
            }),
            lead({
                id: 'mine',
                conversation_state: 'taken',
                conversation_control: { state: 'taken', taken_by: { id: 7, display_name: 'Ana' }, taken_at: '2026-10-05T14:00:00Z' },
            }),
            // Contrato viejo (sin conversation_control): cae a conversation_state.
            lead({ id: 'legacy', conversation_state: 'taken' }),
            lead({ id: 'tp', conversation_state: 'takeover_pending' }),
            lead({ id: 'rp', conversation_state: 'release_pending' }),
            lead({ id: 'err', conversation_state: 'error' }),
            lead({ id: 'active', conversation_state: 'active' }),
            lead({ id: 'none', conversation_state: null }),
        ]);
        renderInbox();
        const rows = screen.getAllByTestId('lead-row');
        const label = (row: HTMLElement) => within(row).queryByTestId('lead-conversation')?.textContent ?? null;
        expect(rows.map(label)).toEqual([
            'Tomada por QA Owner',
            'Tomada por vos',
            'Conversación tomada',
            'Tomando la conversación…',
            'Reactivando el bot…',
            'Error de control del bot',
            null,
            null,
        ]);
        expect(within(rows[0]).getByText('Asignado a Bea Paz')).toBeInTheDocument();
    });

    it('atención y takeover son indicadores separados', () => {
        mockLeads([
            lead({ id: 'att', needs_attention: true }),
            lead({
                id: 'tk',
                conversation_state: 'taken',
                conversation_control: { state: 'taken', taken_by: { id: 9, display_name: 'QA Owner' }, taken_at: null },
            }),
        ]);
        renderInbox();
        const [att, tk] = screen.getAllByTestId('lead-row');
        expect(within(att).getByTestId('lead-attention-badge')).toHaveTextContent('Necesita revisión');
        expect(within(att).queryByTestId('lead-conversation')).not.toBeInTheDocument();
        expect(within(tk).queryByTestId('lead-attention-badge')).not.toBeInTheDocument();
        expect(within(tk).getByTestId('lead-conversation')).toHaveTextContent('Tomada por QA Owner');
    });

    it('no altera el orden del backend ni pide `ordering`', () => {
        mockLeads([
            lead({ id: 'a', conversation_state: 'active' }, { patient_name: 'Primero' }),
            lead({ id: 'b', conversation_state: 'taken' }, { patient_name: 'Segundo' }),
        ]);
        renderInbox();
        const names = screen.getAllByTestId('lead-name').map((link) => link.textContent);
        expect(names).toEqual(['Primero', 'Segundo']);
        expect(lastFilters()).not.toHaveProperty('ordering');
    });
});

describe('inbox operativo (SLICE 2)', () => {
    it('preferred_time se muestra como preferencia, no como reserva', () => {
        mockLeads([lead({}, { reason: 'Limpieza', preferred_time: 'lunes' })]);
        renderInbox();
        const row = screen.getByTestId('lead-row');
        expect(within(row).getByTestId('lead-intent')).toHaveTextContent('Limpieza · Prefiere lunes');
        expect(within(row).getByTestId('lead-appointment-summary')).toHaveTextContent('Sin turno vinculado');
    });

    it('preview del último mensaje del paciente y fallback sin historial (sin usar el resumen)', () => {
        mockLeads([
            lead({ id: 'msg', last_patient_message_text: 'para cuando me agendaste el turno?', last_patient_message_at: '2026-10-05T14:30:00Z' }),
            lead({ id: 'empty' }),
        ]);
        renderInbox();
        const [msg, empty] = screen.getAllByTestId('lead-row');
        expect(within(msg).getByTestId('lead-last-patient-message')).toHaveTextContent('“para cuando me agendaste el turno?” · 05/10/2026 11:30');
        expect(within(empty).getByTestId('lead-last-patient-message')).toHaveTextContent('Sin mensajes del paciente disponibles');
        expect(within(empty).getByTestId('lead-last-patient-message')).not.toHaveTextContent('Resumen del agente');
    });

    it('turno futuro: estado, fecha/hora en zona del Business, servicio y profesional', () => {
        mockLeads([lead({ appointment: appointment() })]);
        renderInbox();
        const summary = screen.getByTestId('lead-appointment-summary');
        expect(summary).toHaveTextContent('Turno confirmado');
        expect(summary).toHaveTextContent('lun 26 oct 2026 · 15:30');
        expect(summary).toHaveTextContent('Limpieza · Dra. X');
    });

    it('turno pasado, cancelado y demás estados sin corregir el persistido', () => {
        mockLeads([
            lead({ id: 'past', appointment: appointment({ start_at: '2026-10-19T18:30:00Z', end_at: '2026-10-19T19:00:00Z', is_upcoming: false, is_past: true }) }),
            lead({ id: 'cancel', appointment: appointment({ status: 'cancelled', is_upcoming: false }) }),
            lead({ id: 'pending', appointment: appointment({ status: 'pending_payment' }) }),
            lead({ id: 'expired', appointment: appointment({ status: 'expired', is_upcoming: false }) }),
            lead({ id: 'done', appointment: appointment({ status: 'completed', is_upcoming: false, is_past: true }) }),
            lead({ id: 'noshow', appointment: appointment({ status: 'no_show', is_upcoming: false, is_past: true, professional_name: null }) }),
        ]);
        renderInbox();
        const labels = screen.getAllByTestId('lead-appointment-summary').map((node) => node.querySelector('p')?.textContent);
        expect(labels).toEqual([
            'Turno pasado · figura confirmado',
            'Turno cancelado',
            'Pendiente de pago',
            'Reserva vencida',
            'Turno completado',
            'No asistió',
        ]);
        const noShow = screen.getAllByTestId('lead-appointment-summary')[5];
        expect(noShow.querySelectorAll('p')[2].textContent).toBe('Limpieza');
    });

    it('textos largos no rompen la fila (clamp/break-words)', () => {
        const long = 'x'.repeat(240);
        mockLeads([lead({ last_patient_message_text: long }, { reason: 'motivo '.repeat(40), preferred_time: 'cualquier día '.repeat(10) })]);
        renderInbox();
        const row = screen.getByTestId('lead-row');
        expect(within(row).getByTestId('lead-last-patient-message')).toHaveClass('line-clamp-2', 'break-words');
        expect(within(row).getByTestId('lead-intent')).toHaveClass('line-clamp-2', 'break-words');
        expect(within(row).getByTestId('lead-name')).toHaveClass('truncate');
    });
});

describe('CTA principal', () => {
    const detail = '/app/turnos/leads/lead-1';
    const taken = { state: 'taken' as const, taken_by: { id: 9, display_name: 'QA Owner' }, taken_at: null };

    it('precedencia completa', () => {
        const cases: Array<[LeadListItem, string, string]> = [
            [lead({ status: 'closed', needs_attention: true, conversation_state: 'error', appointment: appointment() }), 'Ver detalle', detail],
            [lead({ conversation_state: 'error', needs_attention: true, appointment: appointment() }), 'Revisar conversación', detail],
            [lead({ conversation_state: 'takeover_pending', needs_attention: true }), 'Ver conversación', detail],
            [lead({ conversation_state: 'release_pending' }), 'Ver conversación', detail],
            [lead({ conversation_state: 'taken', conversation_control: taken, needs_attention: true, appointment: appointment() }), 'Abrir conversación', detail],
            [lead({ needs_attention: true, appointment: appointment() }), 'Atender', detail],
            [lead({ appointment: appointment() }), 'Ver turno', '/app/turnos/turnos?date=2026-10-26&appointment=appt-1'],
            [lead(), 'Gestionar turno', `${detail}#turno`],
        ];
        for (const [item, label, href] of cases) {
            expect(resolveLeadCta(item, ALL_PERMS)).toMatchObject({ label, href });
        }
    });

    it('conversation_control tiene prioridad sobre conversation_state', () => {
        const item = lead({ conversation_state: 'active', conversation_control: { state: 'error', taken_by: null, taken_at: null } });
        expect(resolveLeadCta(item, ALL_PERMS).label).toBe('Revisar conversación');
    });

    it('permisos: sin manage_leads o manage_appointments no ofrece Gestionar turno; sin view_appointments Ver turno queda en el Lead', () => {
        const none = { ...ALL_PERMS, canManage: false, canManageAppointments: false, canViewAppointments: false };
        expect(resolveLeadCta(lead(), { ...ALL_PERMS, canManage: false })).toMatchObject({ label: 'Ver detalle', href: detail });
        expect(resolveLeadCta(lead(), { ...ALL_PERMS, canManageAppointments: false })).toMatchObject({ label: 'Ver detalle', href: detail });
        expect(resolveLeadCta(lead({ appointment: appointment() }), none)).toMatchObject({ label: 'Ver turno', href: `${detail}#turno` });
    });

    it('la CTA se renderiza como link propio, separado del nombre, y no ejecuta acciones', () => {
        mockLeads([
            lead({ id: 'a', needs_attention: true }),
            lead({ id: 'b', appointment: appointment() }),
            lead({ id: 'c' }),
        ]);
        renderInbox({ canManage: true, canManageAppointments: true, canViewAppointments: true });
        const ctas = screen.getAllByTestId('lead-cta');
        expect(ctas.map((cta) => [cta.textContent, cta.getAttribute('href')])).toEqual([
            ['Atender', '/app/turnos/leads/a'],
            ['Ver turno', '/app/turnos/turnos?date=2026-10-26&appointment=appt-1'],
            ['Gestionar turno', '/app/turnos/leads/c#turno'],
        ]);
        expect(ctas[0]).toHaveAccessibleName('Atender: Ana Pérez');
        for (const row of screen.getAllByTestId('lead-row')) {
            expect(row.querySelector('a a, a button, button a')).toBeNull();
        }
    });

    it('la página pasa los permisos de la sesión', async () => {
        getSessionMock.mockResolvedValue(session({ permissions: { manage_leads: true, manage_appointments: true } }));
        mockLeads([lead()]);
        render(await LeadsPage());
        expect(screen.getByTestId('lead-cta')).toHaveTextContent('Gestionar turno');

        getSessionMock.mockResolvedValue(session({}));
        const element = await LeadsPage();
        expect(element.props).toMatchObject({ canManage: false, canManageAppointments: false, canViewAppointments: false });
    });
});
