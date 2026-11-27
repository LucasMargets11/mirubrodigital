import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { AnchorHTMLAttributes } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// PROD-08D: consumo comercial y métricas operativas de Recepcionista IA en el
// detalle del cliente de Platform Admin, junto a la configuración del agente.

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
// PROD-09B: la preparación tiene su propio suite (receptionist-readiness).
vi.mock('@/components/admin/receptionist-readiness-section', () => ({ ReceptionistReadinessSection: () => null }));
// PROD-08E2: conexiones WhatsApp tienen su propio suite.
vi.mock('@/components/admin/admin-whatsapp-connections-section', () => ({ AdminWhatsAppConnectionsSection: () => null }));

import { ClienteDetailContent } from '@/app/admin/clientes/[clienteId]/cliente-detail-content';
import type { AdminAIUsageOverview, AIUsageSummary, OperationalMetrics } from '@/features/reception/types';
import type { AdminClientDetail } from '@/lib/admin/types';
import { ApiError, apiGet } from '@/lib/api/client';

const getMock = vi.mocked(apiGet);

const base = (id: number) => `/api/v1/platform-admin/clients/${id}`;
const MERCHANT_USAGE = '/api/v1/ai-usage/';

function client(id = 7, name = 'Clínica Sol'): AdminClientDetail {
    return {
        id, name, slug: `c-${id}`, status: 'active', service_type: 'management', country: 'AR', currency: 'ARS',
        created_at: null, activated_at: null, trial_starts_at: null, trial_ends_at: null, owner: null,
        members: [], member_count: 0, branch_count: 0, subscription: null, risk_badges: [],
        recent_payments: [], recent_events: [], recent_audit: [], notes: [], billing_profile: null,
        support_summary: {
            total_tickets: 0, open_tickets: 0, resolved_tickets: 0, last_ticket_at: null,
            last_ticket_reference: null, recent_tickets: [],
        },
    };
}

function summary(overrides: Partial<AIUsageSummary> = {}): AIUsageSummary {
    return {
        contract_version: 1,
        evaluated_at: '2026-11-26T12:00:00+00:00',
        status: 'available',
        reason: null,
        can_start_new_session: true,
        unit: 'ai_session_24h',
        source: { product: 'reception', service_type: 'reception', plan_code: 'reception', usage_tier: 'reception_300', policy_kind: 'catalog' },
        period: { start: '2026-11-01T03:00:00+00:00', end: '2026-12-01T03:00:00+00:00' },
        sessions: { included: 300, used: 120, available_included: 180 },
        hard_cap: { max_sessions: 300, remaining_sessions: 180 },
        overage: { enabled: false, unit_price: null, spend_limit: 0, max_sessions: 0, used_sessions: 0, amount: '0', currency: 'ARS' },
        scheduled_change: null,
        ...overrides,
    };
}

function usage(code: string, s: AIUsageSummary | null = summary()): AdminAIUsageOverview {
    return {
        business_id: 7,
        evaluated_at: '2026-11-26T12:00:00+00:00',
        summary: s,
        source_subscription: code === 'no_ai_subscription' ? null : {
            id: 'sub-1', product: 'reception', service_type: 'reception', plan_code: 'reception', usage_tier: 'reception_300',
            status: code === 'subscription_suspended' ? 'suspended' : 'active', provider: 'manual', billing_cycle: 'monthly',
            complimentary: false, current_period_start: '2026-11-01T03:00:00+00:00', current_period_end: '2026-12-01T03:00:00+00:00',
            grace_until: null, cancel_at_period_end: false, canceled_at: null,
        },
        diagnosis: { code, subscription_id: code === 'no_ai_subscription' ? null : 'sub-1', candidates: [] },
        scope: 'commercial_authorization_only',
    };
}

type MetricsOverrides = {
    whatsapp?: Partial<OperationalMetrics['whatsapp']>;
    openai_activity?: Partial<OperationalMetrics['openai_activity']>;
    openai_costs?: Partial<OperationalMetrics['openai_costs']>;
};

function metrics(o: MetricsOverrides = {}): OperationalMetrics {
    return {
        contract_version: 1,
        business_id: 7,
        period: { timezone: 'America/Argentina/Buenos_Aires', date_from: '2026-10-28', date_to: '2026-11-26', days: 30 },
        openai_activity: {
            executions: 40,
            by_status: { succeeded: 38, failed: 1, unknown: 1 },
            tokens: {
                input: { total: 51234, reported: 40, unknown: 0 },
                output: { total: 8765, reported: 40, unknown: 0 },
                cached_input: { total: 1000, reported: 40, unknown: 0 },
            },
            latency_ms: { reported: 40, average: 812.5, p95: 1900, p95_min_samples: 20 },
            ...o.openai_activity,
        },
        openai_costs: {
            currency: 'USD', kind: 'estimated', estimated_total: '0.1234000000', complete: true,
            costed_executions: 40, uncosted_executions: 0,
            uncosted_reasons: { tokens_unknown: 0, cached_tokens_unknown: 0, no_rate: 0, ambiguous_rate: 0 },
            ...o.openai_costs,
        },
        whatsapp: {
            available: true,
            totals: { messages: 150, inbound: 90, outbound: 60, ai_generated: null, automated_non_ai: null },
            by_sender: { patient: 90, bot: 55, staff: 5 },
            outbound_status: { sent: 4, delivered: 20, read: 33, failed: 2, unknown: 1 },
            conversations: { with_activity: 25, leads_with_activity: 24 },
            handoffs: { requested: 6, bot_paused_for_reception: 4, takeovers_applied: 3, releases_applied: 2 },
            staff_messages: { requested: 5, queued_in_agent: 4, pending: 0, failed: 1 },
            coverage: { has_agent_channel: true, sync_observed: true, leads_at_message_cap: 0 },
            ...o.whatsapp,
        },
    };
}

const UNKNOWN_WHATSAPP: Partial<OperationalMetrics['whatsapp']> = {
    available: false,
    totals: { messages: null, inbound: null, outbound: null, ai_generated: null, automated_non_ai: null },
    by_sender: { patient: null, bot: null, staff: null },
    outbound_status: { sent: null, delivered: null, read: null, failed: null, unknown: null },
    conversations: { with_activity: null, leads_with_activity: null },
    handoffs: { requested: null, bot_paused_for_reception: null, takeovers_applied: null, releases_applied: null },
    staff_messages: { requested: 0, queued_in_agent: 0, pending: 0, failed: 0 },
    coverage: { has_agent_channel: false, sync_observed: false, leads_at_message_cap: 0 },
};

function apiError(status: number, payload: Record<string, unknown> = {}) {
    return new ApiError('error', status, payload);
}

type Routes = { config?: unknown; usage?: unknown; metrics?: unknown };

/** Respuesta por ruta; un `Error` se rechaza. Rutas no previstas fallan el test. */
function routes(id: number, r: Routes) {
    const table: Array<[string, unknown]> = [
        [`${base(id)}/receptionist-config/`, r.config ?? { config: null }],
        [`${base(id)}/ai-usage/`, r.usage ?? usage('ok')],
        [`${base(id)}/operational-metrics/`, r.metrics ?? metrics()],
    ];
    return table;
}

function serve(...tables: Array<Array<[string, unknown]>>) {
    getMock.mockImplementation(async (path: string) => {
        const hit = tables.flat().find(([prefix]) => path.startsWith(prefix));
        if (!hit) throw new Error(`unexpected GET ${path}`);
        if (hit[1] instanceof Error) throw hit[1];
        return hit[1];
    });
}

const section = async (title: string) => {
    const heading = await screen.findByRole('heading', { name: title });
    return heading.closest('div.rounded-xl') as HTMLElement;
};
const usageSection = () => section('Consumo comercial de IA');
const metricsSection = () => section('Métricas operativas');

const getPaths = () => getMock.mock.calls.map(([path]) => path as string);

beforeEach(() => {
    getMock.mockReset();
});

describe('Platform Admin — consumo comercial de IA', () => {
    it('reutiliza el panel de consumo con datos administrativos y nunca consulta el endpoint del comercio', async () => {
        serve(routes(7, {}));
        render(<ClienteDetailContent client={client()} />);

        const card = await usageSection();
        expect(await within(card).findByText('Conversaciones del período')).toBeInTheDocument();
        expect(within(card).getByText('Recepcionista 300')).toBeInTheDocument();
        expect(within(card).getByText(/Quedan 180 conversaciones incluidas/)).toBeInTheDocument();
        expect(within(card).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '40');
        expect(within(card).getByText('Habilitado')).toBeInTheDocument();
        expect(within(card).getByText('Catálogo (cupo fijo)')).toBeInTheDocument();
        expect(within(card).getByText(/300 sesiones \(quedan 180\)/)).toBeInTheDocument();
        expect(within(card).getByText('No habilitados')).toBeInTheDocument();

        expect(getPaths()).toContain(`${base(7)}/ai-usage/`);
        expect(getPaths()).not.toContain(MERCHANT_USAGE);
        expect(getPaths().every((p) => p.startsWith(base(7)))).toBe(true);
    });

    it('cupo agotado sin lectura de sesiones: no inventa ceros', async () => {
        serve(routes(7, { usage: usage('quota_exhausted', summary({
            status: 'exhausted', reason: 'hard_cap_reached', can_start_new_session: false,
            period: null, sessions: null, hard_cap: null, overage: null,
        })) }));
        render(<ClienteDetailContent client={client()} />);

        const card = await usageSection();
        expect(await within(card).findByText('Sin datos de sesiones del período.')).toBeInTheDocument();
        expect(within(card).getByText(/no inicia conversaciones nuevas/)).toBeInTheDocument();
        expect(within(card).getByText('Cupo agotado')).toBeInTheDocument();
        expect(within(card).queryByRole('progressbar')).not.toBeInTheDocument();
        expect(within(card).queryByText(/0 de 0|de 0/)).not.toBeInTheDocument();
        expect(within(card).getAllByText('Sin datos').length).toBeGreaterThan(0);
    });

    it('suspendido: texto administrativo y diagnóstico', async () => {
        serve(routes(7, { usage: usage('subscription_suspended', summary({
            status: 'suspended', reason: 'suspended', can_start_new_session: false,
            period: null, sessions: null, hard_cap: null, overage: null,
        })) }));
        render(<ClienteDetailContent client={client()} />);

        const card = await usageSection();
        expect(await within(card).findByText('Recepcionista IA sin acceso vigente')).toBeInTheDocument();
        expect(within(card).getByText('El servicio está suspendido o fuera de su período bonificado.')).toBeInTheDocument();
        expect(within(card).queryByText(/Revisá tu plan/)).not.toBeInTheDocument();
        expect(within(card).getByText('Suscripción suspendida')).toBeInTheDocument();
        expect(within(card).getByText(/^suspended/)).toBeInTheDocument();
    });

    it('no contratado y política no configurada', async () => {
        const empty = { period: null, sessions: null, hard_cap: null, overage: null, can_start_new_session: false };
        serve(routes(7, { usage: usage('no_ai_subscription', summary({ ...empty, status: 'not_contracted', reason: 'no_ai_entitlement', source: null })) }));
        const { unmount } = render(<ClienteDetailContent client={client()} />);
        let card = await usageSection();
        expect(await within(card).findByText('Sin servicio de IA contratado')).toBeInTheDocument();
        expect(within(card).getByText('El cliente no tiene un servicio de IA contratado.')).toBeInTheDocument();
        expect(within(card).getByText('Sin suscripción de IA')).toBeInTheDocument();
        unmount();

        serve(routes(7, { usage: usage('custom_policy_missing', summary({ ...empty, status: 'policy_not_configured', reason: 'manual_contract_required' })) }));
        render(<ClienteDetailContent client={client()} />);
        card = await usageSection();
        expect(await within(card).findByText('Cupo pendiente de configuración')).toBeInTheDocument();
        expect(within(card).getByText('Sin política personalizada')).toBeInTheDocument();
    });
});

describe('Platform Admin — métricas operativas', () => {
    it('métricas completas: WhatsApp, derivaciones, IA y costo estimado', async () => {
        serve(routes(7, {}));
        render(<ClienteDetailContent client={client()} />);

        const card = await metricsSection();
        expect(await within(card).findByText('Recibidos')).toBeInTheDocument();
        expect(within(card).getByText('90')).toBeInTheDocument();
        expect(within(card).getByText('Bot 55 · Recepción 5')).toBeInTheDocument();
        expect(within(card).getByText('Derivaciones solicitadas').nextSibling).toHaveTextContent('6');
        expect(within(card).getByText('Leídos').nextSibling).toHaveTextContent('33');
        expect(within(card).getByText('38 ok · 1 fallidas · 1 desconocidas')).toBeInTheDocument();
        expect(within(card).getByText('51.234 / 8.765')).toBeInTheDocument();
        expect(within(card).getByText('812,5 ms')).toBeInTheDocument();
        expect(within(card).getByText('p95 1.900 ms')).toBeInTheDocument();
        expect(within(card).getByText(/US\$\s?0,1234/)).toBeInTheDocument();
        expect(within(card).getByText('Completo: 40 ejecuciones estimadas.')).toBeInTheDocument();
        expect(within(card).getByText(/No es facturación/)).toBeInTheDocument();
        // Meta: desconocido, nunca 0.
        expect(within(card).getByText('Meta / WhatsApp').parentElement?.parentElement).toHaveTextContent('Sin datos');
        // Sin rango elegido, el backend decide (30 días) y se muestra su período.
        expect(getPaths()).toContain(`${base(7)}/operational-metrics/`);
        expect(within(card).getByText(/Del 28\/10\/2026 al 26\/11\/2026 \(30 días/)).toBeInTheDocument();
        expect(within(card).getByLabelText('Desde')).toHaveValue('2026-10-28');
    });

    it('métricas parciales: costo parcial con motivos y p95 sin muestras suficientes', async () => {
        serve(routes(7, { metrics: metrics({
            openai_activity: {
                executions: 10,
                by_status: { succeeded: 8, failed: 2, unknown: 0 },
                tokens: {
                    input: { total: 900, reported: 7, unknown: 3 },
                    output: { total: 300, reported: 7, unknown: 3 },
                    cached_input: { total: 0, reported: 7, unknown: 3 },
                },
                latency_ms: { reported: 10, average: 500, p95: null, p95_min_samples: 20 },
            },
            openai_costs: {
                estimated_total: '0.0100000000', complete: false, costed_executions: 6, uncosted_executions: 4,
                uncosted_reasons: { tokens_unknown: 3, cached_tokens_unknown: 0, no_rate: 1, ambiguous_rate: 0 },
            },
        }) }));
        render(<ClienteDetailContent client={client()} />);

        const card = await metricsSection();
        expect(await within(card).findByText('Parcial: 4 ejecuciones sin estimar.')).toBeInTheDocument();
        expect(within(card).getByText('Sin estimar: 3 sin tokens informados · 1 sin tarifa verificada.')).toBeInTheDocument();
        expect(within(card).getByText('p95 con al menos 20 muestras')).toBeInTheDocument();
        expect(within(card).getByText('Entrada / salida · sin informar en 3 ejecuciones')).toBeInTheDocument();
    });

    it('datos desconocidos y costos sin datos: nunca se muestran como cero', async () => {
        serve(routes(7, { metrics: metrics({
            whatsapp: UNKNOWN_WHATSAPP,
            openai_activity: {
                executions: 2,
                by_status: { succeeded: 0, failed: 0, unknown: 2 },
                tokens: {
                    input: { total: null, reported: 0, unknown: 2 },
                    output: { total: null, reported: 0, unknown: 2 },
                    cached_input: { total: null, reported: 0, unknown: 2 },
                },
                latency_ms: { reported: 0, average: null, p95: null, p95_min_samples: 20 },
            },
            openai_costs: {
                estimated_total: '0E-10', complete: false, costed_executions: 0, uncosted_executions: 2,
                uncosted_reasons: { tokens_unknown: 2, cached_tokens_unknown: 0, no_rate: 0, ambiguous_rate: 0 },
            },
        }) }));
        render(<ClienteDetailContent client={client()} />);

        const card = await metricsSection();
        expect(await within(card).findByText(/Sin datos de WhatsApp: el cliente no tiene canal del agente/)).toBeInTheDocument();
        expect(within(card).getByText('Recibidos').parentElement?.parentElement).toHaveTextContent('Sin datos');
        expect(within(card).getByText('Derivaciones solicitadas').nextSibling).toHaveTextContent('Sin datos');
        expect(within(card).getByText('Tokens reportados').parentElement?.parentElement).toHaveTextContent('Sin datos');
        expect(within(card).getByText('Latencia promedio').parentElement?.parentElement).toHaveTextContent('Sin datos');
        expect(within(card).getByText('Ninguna ejecución pudo estimarse.')).toBeInTheDocument();
        expect(within(card).getByText('OpenAI (estimado)').parentElement?.parentElement).toHaveTextContent('Sin datos');
        expect(within(card).queryByText(/US\$/)).not.toBeInTheDocument();
    });

    it('cambio de rango: consulta el rango elegido y valida los límites antes de pedir', async () => {
        serve(routes(7, {}));
        render(<ClienteDetailContent client={client()} />);

        const card = await metricsSection();
        await within(card).findByText('Recibidos');
        fireEvent.change(within(card).getByLabelText('Desde'), { target: { value: '2026-11-01' } });
        await waitFor(() => expect(getPaths()).toContain(
            `${base(7)}/operational-metrics/?date_from=2026-11-01&date_to=2026-11-26`,
        ));

        const before = getMock.mock.calls.length;
        fireEvent.change(within(card).getByLabelText('Desde'), { target: { value: '2026-12-01' } });
        expect(await within(card).findByRole('alert')).toHaveTextContent('anterior o igual');
        fireEvent.change(within(card).getByLabelText('Desde'), { target: { value: '2026-01-01' } });
        expect(await within(card).findByRole('alert')).toHaveTextContent('92 días');
        expect(getMock.mock.calls.length).toBe(before);
    });
});

describe('Platform Admin — integración de secciones', () => {
    it('permisos administrativos: 403 en consumo y métricas con textos propios', async () => {
        serve(routes(7, { usage: apiError(403, { detail: 'forbidden' }), metrics: apiError(403, { detail: 'forbidden' }) }));
        render(<ClienteDetailContent client={client()} />);

        expect(await within(await usageSection()).findByText('Tu rol de Platform Admin no puede ver el consumo de IA.')).toBeInTheDocument();
        expect(await within(await metricsSection()).findByText(/no puede ver las métricas operativas/)).toBeInTheDocument();
    });

    it('errores independientes: falla el consumo y siguen la configuración y las métricas', async () => {
        serve(routes(7, { usage: apiError(500), config: { config: null } }));
        render(<ClienteDetailContent client={client()} />);

        expect(await within(await usageSection()).findByText('No pudimos cargar el consumo')).toBeInTheDocument();
        expect(await within(await metricsSection()).findByText('Recibidos')).toBeInTheDocument();
        expect(await screen.findByRole('button', { name: 'Crear borrador' })).toBeInTheDocument();
    });

    it('error de métricas no afecta al consumo ni a la configuración', async () => {
        serve(routes(7, { metrics: new Error('network') }));
        render(<ClienteDetailContent client={client()} />);

        expect(await within(await metricsSection()).findByText(/No pudimos cargar las métricas/)).toBeInTheDocument();
        expect(await within(await usageSection()).findByText('Conversaciones del período')).toBeInTheDocument();
        expect(await screen.findByRole('button', { name: 'Crear borrador' })).toBeInTheDocument();
    });

    it('cliente sin Recepcionista (404 de dominio): no se consultan consumo ni métricas', async () => {
        serve(routes(7, { config: apiError(404, { code: 'client_not_found', detail: 'Cliente no encontrado.' }) }));
        render(<ClienteDetailContent client={client()} />);

        await waitFor(() => expect(getPaths()).toContain(`${base(7)}/receptionist-config/`));
        await waitFor(() => expect(screen.queryByRole('heading', { name: 'Recepcionista IA' })).not.toBeInTheDocument());
        expect(screen.queryByRole('heading', { name: 'Consumo comercial de IA' })).not.toBeInTheDocument();
        expect(screen.queryByRole('heading', { name: 'Métricas operativas' })).not.toBeInTheDocument();
        expect(getPaths()).toEqual([`${base(7)}/receptionist-config/`]);
    });

    it('cambio de cliente: consultas y datos por cliente, sin mezclar', async () => {
        serve(
            routes(7, {}),
            routes(8, {
                usage: usage('subscription_suspended', summary({ status: 'suspended', reason: 'suspended', period: null, sessions: null, hard_cap: null, overage: null })),
                metrics: metrics({ whatsapp: UNKNOWN_WHATSAPP }),
            }),
        );
        const { rerender } = render(<ClienteDetailContent client={client(7)} />);
        expect(await within(await usageSection()).findByText('Conversaciones del período')).toBeInTheDocument();
        expect(await within(await metricsSection()).findByText('90')).toBeInTheDocument();

        rerender(<ClienteDetailContent client={client(8, 'Spa Luna')} />);
        expect(await within(await usageSection()).findByText('Recepcionista IA sin acceso vigente')).toBeInTheDocument();
        const card = await metricsSection();
        expect(await within(card).findByText(/Sin datos de WhatsApp/)).toBeInTheDocument();
        expect(within(card).queryByText('90')).not.toBeInTheDocument();
        expect(screen.queryByText('Conversaciones del período')).not.toBeInTheDocument();
        expect(getPaths()).toContain(`${base(8)}/ai-usage/`);
        expect(getPaths()).toContain(`${base(8)}/operational-metrics/`);
        expect(getPaths()).not.toContain(MERCHANT_USAGE);
    });
});
