import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { AnchorHTMLAttributes } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// LEADS 05A: bandeja `/app/turnos/leads`. Gating (flag `leads` + `view_leads`),
// render, estados, filtros server-side, búsqueda, paginación y navegación.

vi.mock('next/navigation', () => ({ redirect: vi.fn(), useRouter: () => ({ push: vi.fn() }) }));

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
import type { LeadFilters, LeadListItem } from '@/features/leads/types';

import LeadsPage from '../page';
import LeadDetailPage from '../[id]/page';
import { LEADS_PAGE_SIZE, LeadsInboxClient } from '../leads-inbox-client';

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

function renderInbox() {
    return render(<LeadsInboxClient currentUserId={7} businessTimeZone={TZ} />);
}

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
        expect(within(row).getByText('Quiere un turno para corte')).toBeInTheDocument();
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
        expect(within(rows[0]).getByText('Resumen del agente')).toBeInTheDocument();
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
        expect(within(pending).getByText('Atención pendiente')).toBeInTheDocument();
        expect(pending).toHaveAttribute('data-attention', 'pending');
        expect(within(pending).getByText('Urgente')).toBeInTheDocument();
        expect(within(pending).getByText('Sin asignar')).toBeInTheDocument();
        expect(within(acked).queryByText('Atención pendiente')).not.toBeInTheDocument();
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
        const names = screen.getAllByTestId('lead-row').map((row) => row.querySelector('p')?.textContent);
        expect(names).toEqual(['Primero', 'Segundo']);
    });

    it('cada fila navega a la ruta de detalle', () => {
        renderInbox();
        expect(screen.getByTestId('lead-row')).toHaveAttribute('href', '/app/turnos/leads/lead-1');
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
            assignedTo: undefined, customer: undefined, q: undefined, limit: LEADS_PAGE_SIZE, offset: 0,
        });
    });

    it('cada filtro se traduce al parámetro de la API', () => {
        renderInbox();
        fireEvent.change(screen.getByLabelText('Atención'), { target: { value: 'true' } });
        fireEvent.change(screen.getByLabelText('Urgencia'), { target: { value: 'false' } });
        fireEvent.change(screen.getByLabelText('Estado'), { target: { value: 'closed' } });
        fireEvent.change(screen.getByLabelText('Resultado'), { target: { value: 'spam' } });
        fireEvent.change(screen.getByLabelText('Canal'), { target: { value: 'whatsapp_agent' } });
        fireEvent.change(screen.getByLabelText('Cliente'), { target: { value: 'unlinked' } });
        fireEvent.change(screen.getByLabelText('Asignación'), { target: { value: 'unassigned' } });
        expect(lastFilters()).toMatchObject({
            needsAttention: true, urgency: false, status: 'closed', outcome: 'spam', source: 'whatsapp_agent',
            customer: 'unlinked', assignedTo: 'unassigned', offset: 0,
        });

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
        fireEvent.change(screen.getByLabelText('Estado'), { target: { value: 'new' } });
        expect(lastFilters().offset).toBe(0);
    });

    it('sin paginación cuando todo entra en una página', () => {
        renderInbox();
        expect(screen.queryByRole('navigation', { name: 'Paginación' })).not.toBeInTheDocument();
    });
});

describe('control de la conversación (TAKEOVER 05B)', () => {
    it('badge secundario solo para taken / pending / error; active y sin agente sin ruido', () => {
        mockLeads([
            lead({ id: 'taken', conversation_state: 'taken' }),
            lead({ id: 'tp', conversation_state: 'takeover_pending' }),
            lead({ id: 'rp', conversation_state: 'release_pending' }),
            lead({ id: 'err', conversation_state: 'error' }),
            lead({ id: 'active', conversation_state: 'active' }),
            lead({ id: 'none', conversation_state: null }),
        ]);
        renderInbox();
        const rows = screen.getAllByTestId('lead-row');
        const badge = (row: HTMLElement) => within(row).queryByTestId('lead-conversation-badge')?.textContent ?? null;
        expect(rows.map(badge)).toEqual(['Humano', 'Procesando', 'Procesando', 'Error de control', null, null]);
    });

    it('no altera el orden del backend ni pide `ordering`', () => {
        mockLeads([
            lead({ id: 'a', conversation_state: 'active' }, { patient_name: 'Primero' }),
            lead({ id: 'b', conversation_state: 'taken' }, { patient_name: 'Segundo' }),
        ]);
        renderInbox();
        const names = screen.getAllByTestId('lead-row').map((row) => row.querySelector('p')?.textContent);
        expect(names).toEqual(['Primero', 'Segundo']);
        expect(lastFilters()).not.toHaveProperty('ordering');
    });
});
