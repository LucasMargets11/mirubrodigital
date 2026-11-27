import { render, screen, waitFor, within } from '@testing-library/react';
import type { AnchorHTMLAttributes } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// PROD-09B: «Preparación del agente», derivada de las queries que el bloque
// Recepcionista ya hace. Sin stubs de secciones: el bloque completo se monta
// para comprobar que no hay requests nuevas.

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
import type {
    AdminAIUsageOverview,
    AdminWhatsAppChannel,
    AIUsageSummary,
    OperationalMetrics,
    ReceptionistConfig,
} from '@/features/reception/types';
import type { AdminClientDetail, AdminMember } from '@/lib/admin/types';
import { ApiError, apiGet } from '@/lib/api/client';

const getMock = vi.mocked(apiGet);
const base = (id: number) => `/api/v1/platform-admin/clients/${id}`;
const OWNER: AdminMember = { user_id: 1, email: 'duenia@example.test', name: 'Dueña', role: 'owner' };

function client(id = 7, owner: AdminMember | null = OWNER): AdminClientDetail {
    return {
        id, name: `Cliente ${id}`, slug: `c-${id}`, status: 'trialing', service_type: 'reception', country: 'AR',
        currency: 'ARS', created_at: null, activated_at: null, trial_starts_at: null, trial_ends_at: null, owner,
        members: owner ? [owner] : [], member_count: owner ? 1 : 0, branch_count: 0, subscription: null,
        risk_badges: [], recent_payments: [], recent_events: [], recent_audit: [], notes: [], billing_profile: null,
        support_summary: {
            total_tickets: 0, open_tickets: 0, resolved_tickets: 0, last_ticket_at: null,
            last_ticket_reference: null, recent_tickets: [],
        },
    } as AdminClientDetail;
}

function config(overrides: Partial<ReceptionistConfig> = {}): ReceptionistConfig {
    return {
        id: 'cfg', assistant_name: 'Sol', business_category: '', business_description: '', custom_instructions: '',
        tone: 'warm', language: 'es-AR', welcome_message: '', operational_info: '', business_hours: '',
        services: [], reference_info: '', faqs: [], handoff_rules: '', status: 'draft', version: 1,
        missing_for_ready: ['business_category', 'business_description'],
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

function usage(code: string, s: AIUsageSummary | null = summary(), subStatus = 'trialing'): AdminAIUsageOverview {
    return {
        business_id: 7, evaluated_at: '2026-11-27T12:00:00+00:00', summary: s,
        source_subscription: code === 'no_ai_subscription' ? null : {
            id: 'sub', product: 'reception', service_type: 'reception', plan_code: 'reception', usage_tier: 'reception_300',
            status: subStatus, provider: 'manual', billing_cycle: null, complimentary: true,
            current_period_start: null, current_period_end: null, grace_until: null, cancel_at_period_end: false, canceled_at: null,
        },
        diagnosis: { code, subscription_id: 'sub', candidates: [] },
        scope: 'commercial_authorization_only',
    };
}

function channel(phone: string, overrides: Partial<AdminWhatsAppChannel> = {}): AdminWhatsAppChannel {
    return {
        id: `ch-${phone}`, provider: 'whatsapp_cloud', phone_number_id: phone, waba_id: '9008', is_active: true,
        created_at: '2026-11-20T15:00:00+00:00', deactivated_at: null,
        agent_instance: { external_id: 'recepcion-prod', name: 'Recepcionista prod', is_enabled: true, disabled_at: null },
        authorization: {
            id: `a-${phone}`, kind: 'business', owned_by_this_business: true, status: 'active', expired: false,
            expires_at: null, revoked_at: null, created_at: null, updated_at: null,
        },
        local_status: 'credential_ready',
        ...overrides,
    };
}

function connections(channels: AdminWhatsAppChannel[]) {
    return {
        contract_version: 1, business_id: 7, evaluated_at: '2026-11-27T12:00:00+00:00', channels,
        external_verification: { performed: false, meta_connectivity: 'unknown', detail: 'Estado local.' },
    };
}

const METRICS = new ApiError('x', 500, {}) as unknown as OperationalMetrics; // la sección de métricas queda en error

type Routes = { config?: unknown; usage?: unknown; connections?: unknown };

function routes(id: number, r: Routes): Record<string, unknown> {
    return {
        [`${base(id)}/receptionist-config/`]: 'config' in r ? r.config : { config: null },
        [`${base(id)}/ai-usage/`]: 'usage' in r ? r.usage : usage('ok'),
        [`${base(id)}/whatsapp-connections/`]: 'connections' in r ? r.connections : connections([]),
        [`${base(id)}/operational-metrics/`]: METRICS,
    };
}

function serve(table: Record<string, unknown>, pending: string[] = []) {
    getMock.mockImplementation((path: string) => {
        const key = Object.keys(table).find((prefix) => path.startsWith(prefix));
        if (!key) return Promise.reject(new Error(`unexpected GET ${path}`));
        if (pending.some((p) => path.startsWith(p))) return new Promise(() => {});
        const value = table[key];
        return value instanceof Error ? Promise.reject(value) : Promise.resolve(value);
    });
}

async function readiness() {
    const heading = await screen.findByRole('heading', { name: 'Preparación del agente' });
    return heading.closest('div.rounded-xl') as HTMLElement;
}

/** Fila por su título; devuelve el texto del badge y el detalle. */
function row(card: HTMLElement, label: string) {
    const item = within(card).getByText(label).closest('li') as HTMLElement;
    return item;
}

async function expectRow(card: HTMLElement, label: string, badge: string, detail?: RegExp) {
    await waitFor(() => expect(row(card, label)).toHaveTextContent(badge));
    if (detail) expect(row(card, label)).toHaveTextContent(detail);
}

const getPaths = () => getMock.mock.calls.map(([path]) => path as string);

beforeEach(() => {
    getMock.mockReset();
});

describe('Platform Admin — Preparación del agente', () => {
    it('cliente recién creado: owner parcial, sin configuración ni canales, nunca «listo»', async () => {
        serve(routes(7, {}));
        render(<ClienteDetailContent client={client()} />);
        const card = await readiness();

        await expectRow(card, 'Cuenta owner y membership', 'Verificación parcial', /No se verifica si vinculó Google ni si ya ingresó/);
        await expectRow(card, 'Acceso comercial vigente', 'Cumplida', /Suscripción trialing \(bonificada\)/);
        await expectRow(card, 'Política IA y cupo disponible', 'Cumplida', /Quedan 280 de 300 sesiones/);
        await expectRow(card, 'Configuración «lista»', 'Pendiente', /Todavía no hay configuración/);
        await expectRow(card, 'Canal WhatsApp activo', 'Pendiente', /No hay canales registrados/);
        await expectRow(card, 'Autorización local vigente', 'Desconocida', /no hay canal/);
        await expectRow(card, 'Instancia asignada y habilitada', 'Desconocida', /no hay canal/);
        expect(within(card).getByRole('status')).toHaveTextContent('4 de 7 condiciones sin cumplir o sin verificar.');
    });

    it('sin owner activo: pendiente', async () => {
        serve(routes(7, {}));
        render(<ClienteDetailContent client={client(7, null)} />);
        await expectRow(await readiness(), 'Cuenta owner y membership', 'Pendiente', /no tiene un owner/);
    });

    it('configuración draft y ready', async () => {
        serve(routes(7, { config: { config: config() } }));
        const { unmount } = render(<ClienteDetailContent client={client()} />);
        await expectRow(await readiness(), 'Configuración «lista»', 'Pendiente', /faltan 2 campos obligatorios/);
        unmount();

        serve(routes(7, { config: { config: config({ status: 'ready', missing_for_ready: [] }) } }));
        render(<ClienteDetailContent client={client()} />);
        await expectRow(await readiness(), 'Configuración «lista»', 'Cumplida');
    });

    it('consumo agotado y suspendido', async () => {
        serve(routes(7, { usage: usage('quota_exhausted', summary({ status: 'exhausted', sessions: null, can_start_new_session: false })) }));
        const { unmount } = render(<ClienteDetailContent client={client()} />);
        let card = await readiness();
        await expectRow(card, 'Política IA y cupo disponible', 'Bloqueada', /Cupo del período agotado/);
        await expectRow(card, 'Acceso comercial vigente', 'Cumplida');
        unmount();

        serve(routes(7, { usage: usage('benefit_expired', summary({ status: 'suspended', sessions: null, period: null }), 'suspended') }));
        render(<ClienteDetailContent client={client()} />);
        card = await readiness();
        await expectRow(card, 'Acceso comercial vigente', 'Bloqueada', /Diagnóstico: benefit_expired/);
        await expectRow(card, 'Política IA y cupo disponible', 'Bloqueada', /suspended/);
    });

    it('canal inactivo y canal con credencial vigente (local, verificación parcial)', async () => {
        serve(routes(7, { connections: connections([channel('111', { is_active: false, local_status: 'channel_not_active', authorization: null })]) }));
        const { unmount } = render(<ClienteDetailContent client={client()} />);
        let card = await readiness();
        await expectRow(card, 'Canal WhatsApp activo', 'Bloqueada', /desactivado/);
        await expectRow(card, 'Autorización local vigente', 'Desconocida', /el canal está desactivado/);
        unmount();

        serve(routes(7, { connections: connections([channel('222')]) }));
        render(<ClienteDetailContent client={client()} />);
        card = await readiness();
        await expectRow(card, 'Canal WhatsApp activo', 'Cumplida');
        await expectRow(card, 'Autorización local vigente', 'Verificación parcial', /no verificada con Meta/);
        await expectRow(card, 'Instancia asignada y habilitada', 'Cumplida', /Recepcionista prod, habilitada/);
        expect(card).toHaveTextContent('Canal evaluado: Phone Number ID 222.');
    });

    it('varios canales: evalúa uno solo y no combina estados de canales distintos', async () => {
        // A: activo pero sin autorización; B: inactivo con autorización vigente e instancia
        // habilitada. Combinarlos daría todo verde: no debe pasar.
        serve(routes(7, { connections: connections([
            channel('333', { authorization: null, local_status: 'whatsapp_authorization_missing' }),
            channel('444', { is_active: false, local_status: 'channel_not_active' }),
        ]) }));
        render(<ClienteDetailContent client={client()} />);
        const card = await readiness();
        await expectRow(card, 'Canal WhatsApp activo', 'Cumplida');
        await expectRow(card, 'Autorización local vigente', 'Pendiente', /no tiene autorización/);
        expect(card).toHaveTextContent('Canal evaluado: Phone Number ID 333 (2 canales registrados');
    });

    it('credencial vigente con instancia deshabilitada: bloqueada en el mismo canal', async () => {
        serve(routes(7, { connections: connections([
            channel('555', { local_status: 'agent_instance_disabled', agent_instance: { external_id: 'x', name: 'Agente', is_enabled: false, disabled_at: null } }),
        ]) }));
        render(<ClienteDetailContent client={client()} />);
        const card = await readiness();
        await expectRow(card, 'Autorización local vigente', 'Verificación parcial');
        await expectRow(card, 'Instancia asignada y habilitada', 'Bloqueada', /Agente, deshabilitada/);
    });

    it('datos parciales, errores y valores desconocidos', async () => {
        serve({
            ...routes(7, {
                usage: usage('algo_nuevo', summary({ status: 'mystery' as AIUsageSummary['status'] })),
                connections: new ApiError('forbidden', 403, {}),
            }),
        });
        render(<ClienteDetailContent client={client()} />);
        const card = await readiness();
        await expectRow(card, 'Acceso comercial vigente', 'Desconocida', /Diagnóstico no reconocido \(algo_nuevo\)/);
        await expectRow(card, 'Política IA y cupo disponible', 'Desconocida', /Estado no reconocido \(mystery\)/);
        await expectRow(card, 'Canal WhatsApp activo', 'Desconocida', /Sin acceso para verificarla/);
        await expectRow(card, 'Instancia asignada y habilitada', 'Desconocida');
    });

    it('mientras cargan consumo y conexiones: desconocidas, no cumplidas', async () => {
        serve(routes(7, {}), [`${base(7)}/ai-usage/`, `${base(7)}/whatsapp-connections/`]);
        render(<ClienteDetailContent client={client()} />);
        const card = await readiness();
        for (const label of ['Acceso comercial vigente', 'Política IA y cupo disponible', 'Canal WhatsApp activo']) {
            expect(row(card, label)).toHaveTextContent('Desconocida');
            expect(row(card, label)).toHaveTextContent('Cargando…');
        }
    });

    it('todo local en verde: sin afirmaciones de conexión y con el aviso de activación automática', async () => {
        serve(routes(7, {
            config: { config: config({ status: 'ready', missing_for_ready: [] }) },
            connections: connections([channel('666')]),
        }));
        render(<ClienteDetailContent client={client()} />);
        const card = await readiness();
        await waitFor(() => expect(within(card).getByRole('status')).toHaveTextContent('Condiciones locales cumplidas.'));
        expect(within(card).getByRole('status')).toHaveTextContent('lo que no se verifica desde Mi Rubro sigue pendiente');
        expect(card).toHaveTextContent('No indica que el agente esté conectado ni operativo.');
        for (const text of ['Conectividad real con Meta', 'Que el proceso del agente esté online', 'Flags del entorno', 'Una conversación real de prueba']) {
            expect(card).toHaveTextContent(text);
        }
        expect(card).toHaveTextContent('no hay un interruptor independiente');
        // Ni el resumen ni los badges afirman conexión u operación (las únicas
        // menciones son las aclaraciones negativas).
        const claims = /conectad|operativ|activad|online|en línea/i;
        expect(within(card).getByRole('status').textContent).not.toMatch(claims);
        for (const item of within(card).getAllByRole('listitem')) {
            const badge = item.querySelector('span.rounded-full');
            if (badge) expect(badge.textContent).not.toMatch(claims);
        }
    });

    it('sin consultas HTTP nuevas: cada endpoint del bloque se pide una sola vez', async () => {
        serve(routes(7, { connections: connections([channel('777')]) }));
        render(<ClienteDetailContent client={client()} />);
        const card = await readiness();
        await expectRow(card, 'Canal WhatsApp activo', 'Cumplida');
        await screen.findByRole('heading', { name: 'Conexiones WhatsApp' });
        await screen.findByRole('heading', { name: 'Consumo comercial de IA' });
        await waitFor(() => expect(getPaths()).toContain(`${base(7)}/operational-metrics/`));
        const counts = getPaths().reduce<Record<string, number>>((acc, p) => ({ ...acc, [p]: (acc[p] ?? 0) + 1 }), {});
        expect(counts).toEqual({
            [`${base(7)}/receptionist-config/`]: 1,
            [`${base(7)}/ai-usage/`]: 1,
            [`${base(7)}/whatsapp-connections/`]: 1,
            [`${base(7)}/operational-metrics/`]: 1,
        });
    });

    it('cambio de cliente: no arrastra datos del anterior', async () => {
        serve({
            ...routes(7, { config: { config: config({ status: 'ready', missing_for_ready: [] }) }, connections: connections([channel('888')]) }),
            ...routes(8, {}),
        });
        const { rerender } = render(<ClienteDetailContent client={client(7)} />);
        let card = await readiness();
        await expectRow(card, 'Configuración «lista»', 'Cumplida');
        expect(card).toHaveTextContent('Phone Number ID 888');

        rerender(<ClienteDetailContent client={client(8, null)} />);
        card = await readiness();
        await expectRow(card, 'Configuración «lista»', 'Pendiente', /Todavía no hay configuración/);
        await expectRow(card, 'Canal WhatsApp activo', 'Pendiente');
        await expectRow(card, 'Cuenta owner y membership', 'Pendiente');
        expect(card).not.toHaveTextContent('888');
    });
});
