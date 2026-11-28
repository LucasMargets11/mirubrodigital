import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { AnchorHTMLAttributes } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// PROD-09C3: interruptor «Atención automática» en «Preparación del agente»
// (Platform Admin), sobre el PATCH admin existente de ReceptionistConfig y la
// misma query que el formulario compartido.

vi.mock('@/lib/api/client', async (importOriginal) => ({
    ...(await importOriginal<typeof import('@/lib/api/client')>()),
    apiGet: vi.fn(),
    apiPost: vi.fn(),
    apiPatch: vi.fn(),
}));
vi.mock('next/link', () => ({
    __esModule: true,
    default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
        <a href={href} {...props}>{children}</a>
    ),
}));
vi.mock('@/components/admin/qr-reviews-card', () => ({ QRResenasCard: () => null }));

import { ClienteDetailContent } from '@/app/admin/clientes/[clienteId]/cliente-detail-content';
import type { AdminAIUsageOverview, AIUsageSummary, ReceptionistConfig } from '@/features/reception/types';
import type { AdminClientDetail, AdminMember } from '@/lib/admin/types';
import { ApiError, apiGet, apiPatch } from '@/lib/api/client';

const getMock = vi.mocked(apiGet);
const patchMock = vi.mocked(apiPatch);
const base = (id: number) => `/api/v1/platform-admin/clients/${id}`;
const configPath = (id: number) => `${base(id)}/receptionist-config/`;
const OWNER: AdminMember = { user_id: 1, email: 'duenia@example.test', name: 'Dueña', role: 'owner' };

function client(id = 7, name = 'Clínica Sol'): AdminClientDetail {
    return {
        id, name, slug: `c-${id}`, status: 'trialing', service_type: 'reception', country: 'AR', currency: 'ARS',
        created_at: null, activated_at: null, trial_starts_at: null, trial_ends_at: null, owner: OWNER,
        members: [OWNER], member_count: 1, branch_count: 0, subscription: null, risk_badges: [],
        recent_payments: [], recent_events: [], recent_audit: [], notes: [], billing_profile: null,
        support_summary: {
            total_tickets: 0, open_tickets: 0, resolved_tickets: 0, last_ticket_at: null,
            last_ticket_reference: null, recent_tickets: [],
        },
    } as AdminClientDetail;
}

function config(overrides: Partial<ReceptionistConfig> = {}): ReceptionistConfig {
    return {
        id: 'cfg', assistant_name: 'Sol', business_category: 'Odontología', business_description: 'Clínica dental.',
        custom_instructions: '', tone: 'warm', language: 'es-AR', welcome_message: 'Hola.', operational_info: '',
        business_hours: '', services: [{ name: 'Limpieza', description: '' }], reference_info: '', faqs: [],
        handoff_rules: '', status: 'ready', automatic_attention_enabled: false, version: 4, missing_for_ready: [],
        created_at: '2026-11-27T10:00:00+00:00', updated_at: '2026-11-27T10:00:00+00:00',
        ...overrides,
    };
}

function summary(overrides: Partial<AIUsageSummary> = {}): AIUsageSummary {
    return {
        contract_version: 1, evaluated_at: '2026-11-27T12:00:00+00:00', status: 'available', reason: null,
        can_start_new_session: true, unit: 'ai_session_24h',
        source: { product: 'reception', service_type: 'reception', plan_code: 'reception', usage_tier: 'reception_300', policy_kind: 'catalog' },
        period: { start: '2026-11-01T03:00:00+00:00', end: '2026-12-01T03:00:00+00:00' },
        sessions: { included: 300, used: 20, available_included: 280 },
        hard_cap: { max_sessions: 300, remaining_sessions: 280 }, overage: null, scheduled_change: null,
        ...overrides,
    };
}

function usage(code = 'ok', s: AIUsageSummary = summary()): AdminAIUsageOverview {
    return {
        business_id: 7, evaluated_at: '2026-11-27T12:00:00+00:00', summary: s,
        source_subscription: {
            id: 'sub', product: 'reception', service_type: 'reception', plan_code: 'reception', usage_tier: 'reception_300',
            status: code === 'subscription_suspended' ? 'suspended' : 'trialing', provider: 'manual', billing_cycle: null,
            complimentary: true, current_period_start: null, current_period_end: null, grace_until: null,
            cancel_at_period_end: false, canceled_at: null,
        },
        diagnosis: { code, subscription_id: 'sub', candidates: [] },
        scope: 'commercial_authorization_only',
    };
}

const CONNECTIONS = {
    contract_version: 1, business_id: 7, evaluated_at: '2026-11-27T12:00:00+00:00', channels: [],
    external_verification: { performed: false, meta_connectivity: 'unknown', detail: 'Estado local.' },
};

type Table = Record<string, unknown>;
let configs: Record<number, ReceptionistConfig | null>;
let usages: Record<number, unknown>;

function serve() {
    getMock.mockImplementation(async (path: string) => {
        const id = Number(/clients\/(\d+)\//.exec(path)?.[1]);
        const table: Table = {
            [configPath(id)]: { config: configs[id] ?? null },
            [`${base(id)}/ai-usage/`]: usages[id] ?? usage(),
            [`${base(id)}/whatsapp-connections/`]: CONNECTIONS,
            [`${base(id)}/operational-metrics/`]: new ApiError('x', 500, {}),
        };
        const key = Object.keys(table).find((prefix) => path.startsWith(prefix));
        if (!key) throw new Error(`unexpected GET ${path}`);
        const value = table[key];
        if (value instanceof Error) throw value;
        return value;
    });
}

async function attention() {
    const heading = await screen.findByRole('heading', { name: 'Atención automática' });
    return heading.closest('section') as HTMLElement;
}
const toggle = async () => within(await attention()).getByRole('switch', { name: 'Atención automática' });

beforeEach(() => {
    getMock.mockReset();
    patchMock.mockReset();
    configs = { 7: config(), 8: config({ id: 'cfg-8', assistant_name: 'Luna', automatic_attention_enabled: true, version: 2 }) };
    usages = {};
    serve();
});

describe('Platform Admin — interruptor de atención automática', () => {
    it('estado inicial pausado, sin afirmaciones de conectividad', async () => {
        render(<ClienteDetailContent client={client()} />);
        const section = await attention();
        expect(within(section).getAllByText('Pausada').length).toBeGreaterThan(0);
        const sw = await toggle();
        expect(sw).toHaveAttribute('aria-checked', 'false');
        expect(sw).not.toBeDisabled();
        expect(section).toHaveTextContent('Habilitada no significa que el agente esté conectado');
        expect(section).not.toHaveTextContent(/está conectad[oa]\b(?! ni)|online\b|funcionando/i);
    });

    it('habilitar: confirma con el comercio, envía solo version y flag, y refleja el backend al responder', async () => {
        let resolve!: (value: unknown) => void;
        patchMock.mockImplementation(() => new Promise((r) => { resolve = r; }));
        render(<ClienteDetailContent client={client()} />);
        fireEvent.click(await toggle());

        const dialog = await screen.findByRole('dialog');
        expect(within(dialog).getByText('¿Habilitar la atención automática?')).toBeInTheDocument();
        expect(dialog).toHaveTextContent('Clínica Sol (ID 7)');
        expect(dialog).toHaveTextContent('No garantiza que el agente esté conectado');
        expect(patchMock).not.toHaveBeenCalled();
        expect(await toggle()).toHaveAttribute('aria-checked', 'false');

        fireEvent.click(within(dialog).getByRole('button', { name: 'Habilitar' }));
        expect(patchMock).toHaveBeenCalledWith(configPath(7), { expected_version: 4, automatic_attention_enabled: true }, undefined);
        // Mientras viaja: nada se da por exitoso y las acciones quedan bloqueadas
        expect(within(dialog).getByRole('button', { name: 'Habilitar' })).toBeDisabled();
        expect(within(dialog).getByRole('button', { name: 'Cancelar' })).toBeDisabled();
        expect(await toggle()).toBeDisabled();
        expect(await toggle()).toHaveAttribute('aria-checked', 'false');

        resolve({ config: config({ automatic_attention_enabled: true, version: 5 }) });
        await waitFor(async () => expect(await toggle()).toHaveAttribute('aria-checked', 'true'));
        const section = await attention();
        expect(section).toHaveTextContent('Atención automática habilitada.');
        expect(within(section).getAllByText('Habilitada').length).toBeGreaterThan(0);
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('pausar con confirmación, aunque el consumo esté agotado y la suscripción suspendida', async () => {
        configs[7] = config({ automatic_attention_enabled: true });
        usages[7] = usage('subscription_suspended', summary({ status: 'suspended', sessions: null, period: null }));
        patchMock.mockResolvedValue({ config: config({ automatic_attention_enabled: false, version: 5 }) });
        render(<ClienteDetailContent client={client()} />);
        await screen.findByText(/Diagnóstico: subscription_suspended/);
        const sw = await toggle();
        expect(sw).toHaveAttribute('aria-checked', 'true');
        expect(sw).not.toBeDisabled();
        fireEvent.click(sw);
        const dialog = await screen.findByRole('dialog');
        expect(within(dialog).getByText('¿Pausar la atención automática?')).toBeInTheDocument();
        expect(dialog).toHaveTextContent('pasan al equipo');
        fireEvent.click(within(dialog).getByRole('button', { name: 'Pausar' }));
        expect(patchMock).toHaveBeenCalledWith(configPath(7), { expected_version: 4, automatic_attention_enabled: false }, undefined);
        await waitFor(async () => expect(await toggle()).toHaveAttribute('aria-checked', 'false'));
    });

    it('cancelar el modal no envía nada ni cambia el estado', async () => {
        render(<ClienteDetailContent client={client()} />);
        fireEvent.click(await toggle());
        fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancelar' }));
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(patchMock).not.toHaveBeenCalled();
        expect(await toggle()).toHaveAttribute('aria-checked', 'false');
    });

    it('configuración en borrador: no se puede habilitar y se explica por qué', async () => {
        configs[7] = config({ status: 'draft' });
        render(<ClienteDetailContent client={client()} />);
        expect(await toggle()).toBeDisabled();
        expect(await attention()).toHaveTextContent('la configuración tiene que estar «lista»');
    });

    it('condiciones pendientes: se informan, pero no bloquean la habilitación', async () => {
        render(<ClienteDetailContent client={{ ...client(), owner: null, members: [] }} />);
        const section = await attention();
        await waitFor(() => expect(section).toHaveTextContent(/condición\(es\) comercial\(es\) o técnica\(s\) sin cumplir/));
        expect(await toggle()).not.toBeDisabled();
    });

    it.each([
        ['403', new ApiError('x', 403, { detail: 'forbidden' }), 'Tu rol de Platform Admin no puede cambiar la atención automática.'],
        ['400', new ApiError('x', 400, { code: 'validation_error', fields: { automatic_attention_enabled: ['x'] } }), 'tiene que estar «lista» para habilitarla'],
        ['500', new ApiError('x', 500, {}), 'No pudimos cambiar la atención automática'],
    ])('error %s del backend: mensaje y estado sin cambios', async (_label, error, text) => {
        patchMock.mockRejectedValue(error);
        render(<ClienteDetailContent client={client()} />);
        fireEvent.click(await toggle());
        fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Habilitar' }));
        expect(await within(await attention()).findByText(new RegExp(text.replace(/[()«»]/g, '.')))).toBeInTheDocument();
        expect(await toggle()).toHaveAttribute('aria-checked', 'false');
        expect(patchMock).toHaveBeenCalledTimes(1);
    });

    it('409: sin reintento ni sobrescritura; recargar es explícito', async () => {
        patchMock.mockRejectedValue(new ApiError('x', 409, { code: 'version_conflict', current_version: 6 }));
        render(<ClienteDetailContent client={client()} />);
        fireEvent.click(await toggle());
        fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Habilitar' }));
        const section = await attention();
        expect(await within(section).findByText(/La configuración cambió desde que la cargaste/)).toBeInTheDocument();
        expect(patchMock).toHaveBeenCalledTimes(1);
        const before = getMock.mock.calls.filter(([p]) => p === configPath(7)).length;
        configs[7] = config({ version: 6, automatic_attention_enabled: true });
        fireEvent.click(within(section).getByRole('button', { name: 'Recargar estado' }));
        await waitFor(async () => expect(await toggle()).toHaveAttribute('aria-checked', 'true'));
        expect(getMock.mock.calls.filter(([p]) => p === configPath(7)).length).toBe(before + 1);
        expect(patchMock).toHaveBeenCalledTimes(1);
    });

    it('formulario con cambios sin guardar: el interruptor los conserva y el formulario guarda sobre la versión nueva', async () => {
        patchMock
            .mockResolvedValueOnce({ config: config({ automatic_attention_enabled: true, version: 5 }) })
            .mockResolvedValueOnce({ config: config({ assistant_name: 'Sol Nueva', automatic_attention_enabled: true, version: 6 }) });
        render(<ClienteDetailContent client={client()} />);
        const name = await screen.findByDisplayValue('Sol');
        fireEvent.change(name, { target: { value: 'Sol Nueva' } });
        expect(screen.getByText('Cambios sin guardar')).toBeInTheDocument();

        fireEvent.click(await toggle());
        fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Habilitar' }));
        await waitFor(async () => expect(await toggle()).toHaveAttribute('aria-checked', 'true'));
        // La edición local sigue y no es un conflicto (solo cambió la atención)
        expect(screen.getByDisplayValue('Sol Nueva')).toBeInTheDocument();
        expect(screen.getByText('Cambios sin guardar')).toBeInTheDocument();
        expect(screen.queryByText('Otra persona guardó cambios en esta configuración')).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));
        await waitFor(() => expect(patchMock).toHaveBeenCalledTimes(2));
        // Solo el contenido editado y la versión que dejó el interruptor
        expect(patchMock.mock.calls[1][1]).toEqual({ assistant_name: 'Sol Nueva', expected_version: 5 });
        expect(await toggle()).toHaveAttribute('aria-checked', 'true');
    });

    it('contenido nuevo del servidor bajo cambios sin guardar: conflicto, nunca se adopta en silencio', async () => {
        patchMock.mockRejectedValue(new ApiError('x', 409, { code: 'version_conflict', current_version: 7 }));
        render(<ClienteDetailContent client={client()} />);
        fireEvent.change(await screen.findByDisplayValue('Sol'), { target: { value: 'Mi edición' } });
        fireEvent.click(await toggle());
        fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Habilitar' }));
        const section = await attention();
        await within(section).findByText(/La configuración cambió/);
        // Otra persona cambió el contenido; recargar no pisa la edición local
        configs[7] = config({ assistant_name: 'Cambio ajeno', version: 7 });
        fireEvent.click(within(section).getByRole('button', { name: 'Recargar estado' }));
        expect(await screen.findByText('Otra persona guardó cambios en esta configuración')).toBeInTheDocument();
        expect(screen.getByDisplayValue('Mi edición')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Guardar cambios' })).toBeDisabled();
    });

    it('ready → draft → ready: el borrador pausa y volver a lista no reactiva', async () => {
        configs[7] = config({ automatic_attention_enabled: true });
        patchMock
            .mockResolvedValueOnce({ config: config({ status: 'draft', automatic_attention_enabled: false, version: 5 }) })
            .mockResolvedValueOnce({ config: config({ status: 'ready', automatic_attention_enabled: false, version: 6 }) });
        render(<ClienteDetailContent client={client()} />);
        expect(await toggle()).toHaveAttribute('aria-checked', 'true');
        fireEvent.click(await screen.findByRole('button', { name: 'Volver a borrador' }));
        const dialog = await screen.findByRole('dialog');
        expect(dialog).toHaveTextContent('también pausa la atención automática');
        expect(dialog).toHaveTextContent('hay que volver a habilitarla en «Preparación del agente»');
        fireEvent.click(within(dialog).getByRole('button', { name: 'Volver a borrador' }));
        await waitFor(async () => expect(await toggle()).toHaveAttribute('aria-checked', 'false'));
        expect(patchMock.mock.calls[0][1]).toEqual({ status: 'draft', expected_version: 4 });

        fireEvent.click(await screen.findByRole('button', { name: 'Marcar como lista' }));
        await waitFor(() => expect(patchMock).toHaveBeenCalledTimes(2));
        // El formulario usa la versión compartida; la atención sigue pausada
        expect(patchMock.mock.calls[1][1]).toEqual({ status: 'ready', expected_version: 5 });
        await screen.findByText('Configuración lista');
        expect(await toggle()).toHaveAttribute('aria-checked', 'false');
        expect(await toggle()).not.toBeDisabled();
    });

    it('estado desconocido (sin el campo): no se puede operar ni se asume habilitada', async () => {
        const unknown = config();
        delete (unknown as Partial<ReceptionistConfig>).automatic_attention_enabled;
        configs[7] = unknown;
        render(<ClienteDetailContent client={client()} />);
        const section = await attention();
        expect(within(section).getAllByText('Estado desconocido').length).toBeGreaterThan(0);
        expect(await toggle()).toBeDisabled();
        expect(await toggle()).toHaveAttribute('aria-checked', 'false');
    });

    it('cambio de cliente: el estado y la versión son los del nuevo cliente', async () => {
        patchMock.mockResolvedValue({ config: config({ id: 'cfg-8', assistant_name: 'Luna', automatic_attention_enabled: false, version: 3 }) });
        const { rerender } = render(<ClienteDetailContent client={client(7)} />);
        expect(await toggle()).toHaveAttribute('aria-checked', 'false');
        rerender(<ClienteDetailContent client={client(8, 'Spa Luna')} />);
        await screen.findByDisplayValue('Luna');
        expect(await toggle()).toHaveAttribute('aria-checked', 'true');
        fireEvent.click(await toggle());
        const dialog = await screen.findByRole('dialog');
        expect(dialog).toHaveTextContent('Spa Luna (ID 8)');
        fireEvent.click(within(dialog).getByRole('button', { name: 'Pausar' }));
        expect(patchMock).toHaveBeenCalledWith(configPath(8), { expected_version: 2, automatic_attention_enabled: false }, undefined);
    });

    it('sin consultas nuevas: la configuración se pide una vez para la preparación y el formulario', async () => {
        render(<ClienteDetailContent client={client()} />);
        await toggle();
        await screen.findByDisplayValue('Sol');
        expect(getMock.mock.calls.filter(([p]) => p === configPath(7))).toHaveLength(1);
    });
});
