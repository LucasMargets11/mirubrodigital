import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { AnchorHTMLAttributes } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// PROD-09E: «Agregar Recepcionista IA» a un comercio existente desde el detalle
// del cliente (Platform Admin), sobre el endpoint PROD-02F5.

const { refresh } = vi.hoisted(() => ({ refresh: vi.fn() }));

vi.mock('@/lib/api/client', async (importOriginal) => ({
    ...(await importOriginal<typeof import('@/lib/api/client')>()),
    apiGet: vi.fn(),
    apiPost: vi.fn(),
    apiPatch: vi.fn(),
}));
vi.mock('@/lib/admin/client', async (importOriginal) => ({
    ...(await importOriginal<typeof import('@/lib/admin/client')>()),
    getAdminClientProvisioningOptions: vi.fn(),
    addServiceToAdminClient: vi.fn(),
}));
vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh }) }));
vi.mock('next/link', () => ({
    __esModule: true,
    default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
        <a href={href} {...props}>{children}</a>
    ),
}));
vi.mock('@/components/admin/qr-reviews-card', () => ({ QRResenasCard: () => null }));
vi.mock('@/components/admin/receptionist-readiness-section', () => ({
    ReceptionistReadinessSection: () => <p>Preparación de Recepcionista</p>,
}));
vi.mock('@/components/admin/admin-whatsapp-connections-section', () => ({
    AdminWhatsAppConnectionsSection: () => <p>Conexiones WhatsApp</p>,
}));
vi.mock('@/components/admin/admin-operational-metrics-section', () => ({
    AdminOperationalMetricsSection: () => <p>Métricas operativas</p>,
}));
vi.mock('@/features/reception/receptionist-config-form', async (importOriginal) => ({
    ...(await importOriginal<typeof import('@/features/reception/receptionist-config-form')>()),
    ReceptionistConfigForm: () => <p>Formulario de configuración</p>,
}));

import { ClienteDetailContent } from '@/app/admin/clientes/[clienteId]/cliente-detail-content';
import { hasActiveTurnosIA } from '@/components/admin/add-reception-service';
import type { AdminAIUsageOverview } from '@/features/reception/types';
import {
    type AdminClientServiceAdditionResponse,
    addServiceToAdminClient,
    getAdminClientProvisioningOptions,
} from '@/lib/admin/client';
import { addCalendarMonths, todayDateOnly } from '@/lib/admin/complimentary-period';
import type { AdminClientDetail, AdminClientProvisioningOptions } from '@/lib/admin/types';
import { ApiError, apiGet, apiPatch, apiPost } from '@/lib/api/client';

const getMock = vi.mocked(apiGet);
const patchMock = vi.mocked(apiPatch);
const postMock = vi.mocked(apiPost);
const optionsMock = vi.mocked(getAdminClientProvisioningOptions);
const addMock = vi.mocked(addServiceToAdminClient);

const base = (id: number) => `/api/v1/platform-admin/clients/${id}`;
const TODAY = todayDateOnly();
const SIX_MONTHS = addCalendarMonths(TODAY, 6);

const OPTIONS: AdminClientProvisioningOptions = {
    services: [
        { value: 'gestion', label: 'Gestión', plans: [{ code: 'gestion_pro', name: 'Gestión Pro' }] },
        {
            value: 'reception', label: 'Recepcionista IA',
            plans: [{
                code: 'reception', name: 'Recepcionista IA',
                usage_tiers: [
                    { code: 'reception_300', name: 'Recepcionista 300' },
                    { code: 'reception_1500', name: 'Recepcionista 1.500' },
                    { code: 'reception_3000', name: 'Recepcionista 3.000' },
                    { code: 'reception_custom', name: 'Recepcionista Custom', custom_allowance: { min: 1, max: 100000 } },
                ],
            }],
        },
    ],
};

function client(id = 7, name = 'Ferretería Sol', overrides: Partial<AdminClientDetail> = {}): AdminClientDetail {
    return {
        id, name, slug: `c-${id}`, status: 'active', service_type: 'gestion', country: 'AR', currency: 'ARS',
        created_at: null, activated_at: null, trial_starts_at: null, trial_ends_at: null, owner: null,
        members: [], member_count: 0, branch_count: 0, subscription: null, risk_badges: [],
        recent_payments: [], recent_events: [], recent_audit: [], notes: [], billing_profile: null,
        support_summary: {
            total_tickets: 0, open_tickets: 0, resolved_tickets: 0, last_ticket_at: null,
            last_ticket_reference: null, recent_tickets: [],
        },
        ...overrides,
    };
}

function usage(candidates: unknown[] = [], source: AdminAIUsageOverview['source_subscription'] = null): AdminAIUsageOverview {
    return {
        business_id: 7, evaluated_at: '2026-11-27T12:00:00+00:00', summary: null, source_subscription: source,
        diagnosis: { code: 'no_ai_subscription', subscription_id: null, candidates }, scope: 'commercial_authorization_only',
    };
}

const NOT_FOUND = new ApiError('x', 404, { code: 'client_not_found', detail: 'Cliente no encontrado.' });
const CONFIG = { config: { id: 'cfg', status: 'draft', automatic_attention_enabled: false, version: 1 } };

type Server = { config: unknown; usage: unknown };

/** Estado del servidor por cliente; mutable para simular el alta. */
function serve(servers: Record<number, Server>) {
    getMock.mockImplementation(async (path: string) => {
        for (const [id, server] of Object.entries(servers)) {
            const value = path === `${base(Number(id))}/receptionist-config/` ? server.config
                : path === `${base(Number(id))}/ai-usage/` ? server.usage : undefined;
            if (value === undefined) continue;
            if (value instanceof Error) throw value;
            return value;
        }
        throw new Error(`unexpected GET ${path}`);
    });
}

const created: AdminClientServiceAdditionResponse = {
    status: 'ok',
    data: {
        business: { id: 7, status: 'active', service_type: 'gestion', default_service: 'gestion' },
        subscription: {
            id: 'rsub-new', service_type: 'reception', plan_code: 'reception', usage_tier: 'reception_300',
            provider: 'manual', status: 'trialing', current_period_start: `${TODAY}T03:00:00+00:00`,
            current_period_end: `${SIX_MONTHS}T03:00:00+00:00`,
        },
        custom_policy: null,
    },
};

const calls = (path: string) => getMock.mock.calls.filter(([p]) => p === path).length;
const addButton = () => screen.findByRole('button', { name: 'Agregar Recepcionista IA' });
const dialog = () => screen.getByRole('dialog', { name: 'Agregar Recepcionista IA' });
const submit = () => fireEvent.click(within(dialog()).getByRole('button', { name: /Agregar Recepcionista IA|Agregando/ }));

async function openModal() {
    fireEvent.click(await addButton());
    const modal = dialog();
    await within(modal).findByLabelText('Nivel de uso');
    return modal;
}

function fill({ tier = 'reception_300', reason = '  Suma Recepcionista  ', sixMonths = true } = {}) {
    const modal = dialog();
    fireEvent.change(within(modal).getByLabelText('Nivel de uso'), { target: { value: tier } });
    if (sixMonths) fireEvent.click(within(modal).getByRole('button', { name: '6 meses' }));
    fireEvent.change(within(modal).getByLabelText('Motivo de la bonificación'), { target: { value: reason } });
}

function renderDetail(props: { client?: AdminClientDetail; canAddReception?: boolean } = {}) {
    return render(
        <ClienteDetailContent client={props.client ?? client()} canAddReception={props.canAddReception ?? true} />,
    );
}

beforeEach(() => {
    getMock.mockReset();
    patchMock.mockReset();
    postMock.mockReset();
    optionsMock.mockReset();
    addMock.mockReset();
    refresh.mockReset();
    optionsMock.mockResolvedValue({ status: 'ok', data: OPTIONS });
});

describe('PROD-09E — Agregar Recepcionista IA', () => {
    it('comercio existente sin Recepcionista: plan fijo, payload del contrato y bloque completo después del alta', async () => {
        const server: Server = { config: NOT_FOUND, usage: usage() };
        serve({ 7: server });
        addMock.mockImplementation(async () => {
            server.config = CONFIG; // la configuración ya no responde 404
            return created;
        });
        renderDetail();
        const modal = await openModal();
        expect(within(modal).getByText('Ferretería Sol (ID 7)')).toBeInTheDocument();
        const tiers = Array.from((within(modal).getByLabelText('Nivel de uso') as HTMLSelectElement).options).map((o) => o.text);
        expect(tiers).toEqual([
            'Seleccioná un nivel de uso', 'Recepcionista 300', 'Recepcionista 1.500', 'Recepcionista 3.000', 'Recepcionista Custom',
        ]);
        // Sin datos comerciales del comercio: ni owner, ni país, ni moneda, ni servicio.
        for (const label of [/Email del owner/i, /País/, /Moneda/, /Servicio/]) {
            expect(within(modal).queryByLabelText(label)).not.toBeInTheDocument();
        }
        fill();
        submit();

        await waitFor(() => expect(addMock).toHaveBeenCalledTimes(1));
        expect(addMock).toHaveBeenCalledWith(7, {
            service_type: 'reception', plan_code: 'reception', complimentary_start: TODAY,
            complimentary_end: SIX_MONTHS, grant_reason: 'Suma Recepcionista', usage_tier: 'reception_300',
        });
        // El bloque existente aparece (preparación, configuración, conexiones, consumo y métricas).
        expect(await screen.findByText('Preparación de Recepcionista')).toBeInTheDocument();
        expect(screen.getByText('Formulario de configuración')).toBeInTheDocument();
        expect(screen.getByText('Conexiones WhatsApp')).toBeInTheDocument();
        expect(screen.getByRole('heading', { name: 'Consumo comercial de IA' })).toBeInTheDocument();
        expect(screen.getByText('Métricas operativas')).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Agregar Recepcionista IA' })).not.toBeInTheDocument();
        expect(refresh).toHaveBeenCalledTimes(1);
        // Sin escrituras sobre la configuración ni la atención automática.
        expect(patchMock).not.toHaveBeenCalled();
        expect(postMock).not.toHaveBeenCalled();
        // El servicio principal del detalle no se toca.
        expect(screen.getByText('gestion')).toBeInTheDocument();
    });

    it('plan personalizado: pide el cupo dentro de los límites y lo envía', async () => {
        serve({ 7: { config: NOT_FOUND, usage: usage() } });
        addMock.mockResolvedValue(created);
        renderDetail();
        await openModal();
        fill({ tier: 'reception_custom' });
        const allowance = within(dialog()).getByLabelText(/Cupo personalizado/);
        fireEvent.change(allowance, { target: { value: '0' } });
        submit();
        expect(await within(dialog()).findByText('Ingresá un número entero entre 1 y 100.000.')).toBeInTheDocument();
        expect(addMock).not.toHaveBeenCalled();
        fireEvent.change(allowance, { target: { value: '750' } });
        submit();
        await waitFor(() => expect(addMock).toHaveBeenCalledWith(7, expect.objectContaining({
            usage_tier: 'reception_custom', custom_included_sessions: 750,
        })));
    });

    it('permisos: sin superadmin no se ofrece', async () => {
        serve({ 7: { config: NOT_FOUND, usage: usage() } });
        renderDetail({ canAddReception: false });
        await waitFor(() => expect(calls(`${base(7)}/receptionist-config/`)).toBe(1));
        expect(screen.queryByRole('button', { name: 'Agregar Recepcionista IA' })).not.toBeInTheDocument();
        expect(screen.queryByRole('heading', { name: 'Recepcionista IA' })).not.toBeInTheDocument();
    });

    it('Recepcionista ya contratada (principal o adicional): muestra el bloque, no la incorporación', async () => {
        serve({ 7: { config: CONFIG, usage: usage() } });
        renderDetail({ client: client(7, 'Clínica', { service_type: 'gestion' }) });
        expect(await screen.findByText('Formulario de configuración')).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Agregar Recepcionista IA' })).not.toBeInTheDocument();
    });

    it('servicio principal Recepcionista sin suscripción no cancelada: se decide por la configuración, no por el servicio', async () => {
        serve({ 7: { config: NOT_FOUND, usage: usage() } });
        renderDetail({ client: client(7, 'Clínica', { service_type: 'reception' }) });
        expect(await addButton()).toBeInTheDocument();
    });

    it('incompatibilidad conocida con Turnos IA o cliente no elegible: no se ofrece', async () => {
        const turnos = usage([{ product: 'appointments_ai', subscription_id: 's', status: 'trialing', eligible: true }]);
        expect(hasActiveTurnosIA(turnos)).toBe(true);
        expect(hasActiveTurnosIA(usage([], {
            id: 's', product: 'appointments_ai', service_type: 'appointments', plan_code: 'appointments_ai',
            usage_tier: 'ai_300', status: 'active', provider: 'manual', billing_cycle: null, complimentary: false,
            current_period_start: null, current_period_end: null, grace_until: null, cancel_at_period_end: false,
            canceled_at: null,
        }))).toBe(true);
        expect(hasActiveTurnosIA(usage([{ product: 'appointments_ai', status: 'canceled' }]))).toBe(false);
        expect(hasActiveTurnosIA(usage())).toBe(false);

        serve({ 7: { config: NOT_FOUND, usage: turnos } });
        const { unmount } = renderDetail();
        expect(await screen.findByText(/Recepcionista IA y Turnos IA no pueden estar activos/)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Agregar Recepcionista IA' })).not.toBeInTheDocument();
        unmount();

        serve({ 8: { config: NOT_FOUND, usage: usage() } });
        renderDetail({ client: client(8, 'Suspendido', { status: 'suspended' }) });
        expect(await screen.findByText(/El estado del cliente \(«suspended»\) no permite agregar servicios/)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Agregar Recepcionista IA' })).not.toBeInTheDocument();
    });

    it('sin poder verificar los servicios de IA: no se ofrece y permite reintentar', async () => {
        const server: Server = { config: NOT_FOUND, usage: new ApiError('x', 500, {}) };
        serve({ 7: server });
        renderDetail();
        expect(await screen.findByText(/No pudimos verificar los servicios de IA del cliente/)).toBeInTheDocument();
        server.usage = usage();
        fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }));
        expect(await addButton()).toBeInTheDocument();
    });

    it('validaciones de nivel, fechas y motivo; no envía nada', async () => {
        serve({ 7: { config: NOT_FOUND, usage: usage() } });
        renderDetail();
        const modal = await openModal();
        submit();
        expect(within(modal).getByText('Seleccioná el nivel de uso.')).toBeInTheDocument();
        expect(within(modal).getByText('Ingresá la fecha de fin.')).toBeInTheDocument();
        expect(within(modal).getByText('Ingresá el motivo de la bonificación.')).toBeInTheDocument();
        fireEvent.change(within(modal).getByLabelText('Fin de la bonificación'), { target: { value: TODAY } });
        fireEvent.change(within(modal).getByLabelText('Motivo de la bonificación'), { target: { value: 'x'.repeat(256) } });
        submit();
        expect(within(modal).getByText('Debe ser posterior a la fecha de inicio.')).toBeInTheDocument();
        expect(within(modal).getByText('El motivo no puede superar los 255 caracteres.')).toBeInTheDocument();
        expect(within(modal).getByLabelText('Motivo de la bonificación')).toHaveAttribute('maxLength', '255');
        expect(addMock).not.toHaveBeenCalled();
    });

    it('cancelar cierra sin enviar', async () => {
        serve({ 7: { config: NOT_FOUND, usage: usage() } });
        renderDetail();
        await openModal();
        fill();
        fireEvent.click(within(dialog()).getByRole('button', { name: 'Cancelar' }));
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(addMock).not.toHaveBeenCalled();
    });

    it('solicitud en curso: controles deshabilitados y sin doble envío ni éxito anticipado', async () => {
        serve({ 7: { config: NOT_FOUND, usage: usage() } });
        let resolve: (value: AdminClientServiceAdditionResponse) => void = () => undefined;
        addMock.mockReturnValue(new Promise((r) => { resolve = r; }));
        renderDetail();
        await openModal();
        fill();
        submit();
        const sending = await within(dialog()).findByRole('button', { name: 'Agregando…' });
        expect(sending).toBeDisabled();
        expect(within(dialog()).getByRole('button', { name: 'Cancelar' })).toBeDisabled();
        expect(within(dialog()).getByLabelText('Motivo de la bonificación')).toBeDisabled();
        fireEvent.click(sending);
        submit();
        expect(addMock).toHaveBeenCalledTimes(1);
        expect(refresh).not.toHaveBeenCalled();
        await act(async () => resolve(created));
        await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
    });

    it('errores de campo: solapamiento de consumo, cupo y forma; conserva el formulario', async () => {
        serve({ 7: { config: NOT_FOUND, usage: usage() } });
        renderDetail();
        await openModal();
        fill({ reason: 'Motivo válido' });
        const detail = 'El negocio tiene consumo de IA en un período vigente al inicio del beneficio; elegí un inicio posterior al fin de ese período.';
        addMock.mockResolvedValueOnce({
            status: 'domain_error', httpStatus: 409,
            error: { code: 'ai_usage_period_overlap', detail, field: 'complimentary_start' },
        });
        submit();
        expect(await within(dialog()).findByText(detail)).toBeInTheDocument();
        expect(within(dialog()).getByLabelText('Motivo de la bonificación')).toHaveValue('Motivo válido');
        expect(within(dialog()).getByLabelText('Nivel de uso')).toHaveValue('reception_300');

        addMock.mockResolvedValueOnce({
            status: 'field_errors', httpStatus: 400, fieldErrors: { complimentary_end: 'Fecha inválida.' },
        });
        submit();
        expect(await within(dialog()).findByText('Fecha inválida.')).toBeInTheDocument();

        addMock.mockResolvedValueOnce({
            status: 'domain_error', httpStatus: 400,
            error: { code: 'complimentary_plan_not_available', detail: 'El plan elegido no está disponible.', field: 'plan_code' },
        });
        submit();
        // Sin selector de plan (plan único): el error va al aviso general.
        expect(await within(dialog()).findByRole('alert')).toHaveTextContent('El plan elegido no está disponible. No se cambió nada.');
        expect(addMock).toHaveBeenCalledTimes(3);
        expect(refresh).not.toHaveBeenCalled();
    });

    it('servicio ya contratado, Turnos IA y cliente no elegible: aviso, recarga explícita y sin reintento', async () => {
        const cases = [
            ['active_complimentary_subscription_conflict', 'El cliente ya tiene una suscripción vigente para este servicio.', 'service_type'],
            ['incompatible_ai_service', 'Recepcionista IA y Turnos IA no pueden estar activos en el mismo negocio.', 'service_type'],
            ['client_status_not_eligible', 'El estado del negocio no permite agregar servicios.', null],
            ['client_not_found', 'Cliente no encontrado.', null],
        ] as const;
        for (const [code, detail, field] of cases) {
            getMock.mockReset();
            addMock.mockReset();
            refresh.mockReset();
            serve({ 7: { config: NOT_FOUND, usage: usage() } });
            addMock.mockResolvedValueOnce({ status: 'domain_error', httpStatus: code === 'client_not_found' ? 404 : 409, error: { code, detail, field } });
            const { unmount } = renderDetail();
            await openModal();
            fill();
            submit();
            const alert = await within(dialog()).findByRole('alert');
            expect(alert, code).toHaveTextContent(`${detail} No se cambió nada.`);
            const before = calls(`${base(7)}/receptionist-config/`);
            fireEvent.click(within(alert).getByRole('button', { name: 'Recargar datos' }));
            await waitFor(() => expect(calls(`${base(7)}/receptionist-config/`)).toBeGreaterThan(before));
            expect(refresh).toHaveBeenCalledTimes(1);
            expect(addMock).toHaveBeenCalledTimes(1);
            unmount();
        }
    });

    it('403 y error de red: aviso sin recarga y formulario conservado', async () => {
        serve({ 7: { config: NOT_FOUND, usage: usage() } });
        renderDetail();
        await openModal();
        fill({ reason: 'Conservar' });
        addMock.mockResolvedValueOnce({ status: 'forbidden' });
        submit();
        expect(await within(dialog()).findByRole('alert')).toHaveTextContent('Solo un superadmin puede agregar servicios.');
        addMock.mockResolvedValueOnce({ status: 'server_error', httpStatus: 0 });
        submit();
        await waitFor(() => expect(within(dialog()).getByRole('alert')).toHaveTextContent('Error de red'));
        expect(within(dialog()).queryByRole('button', { name: 'Recargar datos' })).not.toBeInTheDocument();
        expect(within(dialog()).getByLabelText('Motivo de la bonificación')).toHaveValue('Conservar');
        expect(addMock).toHaveBeenCalledTimes(2);
    });

    it('planes no disponibles: error con reintento y sin Recepcionista en el catálogo', async () => {
        serve({ 7: { config: NOT_FOUND, usage: usage() } });
        optionsMock.mockResolvedValueOnce({ status: 'error', message: 'x' });
        renderDetail();
        fireEvent.click(await addButton());
        expect(await within(dialog()).findByText('No pudimos cargar los planes disponibles.')).toBeInTheDocument();
        expect(within(dialog()).getByRole('button', { name: 'Agregar Recepcionista IA' })).toBeDisabled();
        optionsMock.mockResolvedValueOnce({ status: 'ok', data: { services: [OPTIONS.services[0]] } });
        fireEvent.click(within(dialog()).getByRole('button', { name: 'Reintentar' }));
        expect(await within(dialog()).findByText('Recepcionista IA no está disponible para alta interna.')).toBeInTheDocument();
    });

    it('cambio de cliente: no mezcla formulario ni negocio', async () => {
        serve({ 7: { config: NOT_FOUND, usage: usage() }, 8: { config: NOT_FOUND, usage: usage() } });
        addMock.mockResolvedValue(created);
        const { rerender } = renderDetail({ client: client(7, 'Ferretería Sol') });
        await openModal();
        fill({ reason: 'Para Sol' });
        rerender(<ClienteDetailContent key={8} client={client(8, 'Ferretería Luna')} canAddReception />);
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        const modal = await openModal();
        expect(within(modal).getByText('Ferretería Luna (ID 8)')).toBeInTheDocument();
        expect(within(modal).getByLabelText('Motivo de la bonificación')).toHaveValue('');
        fill({ reason: 'Para Luna' });
        submit();
        await waitFor(() => expect(addMock).toHaveBeenCalledWith(8, expect.objectContaining({ grant_reason: 'Para Luna' })));
    });
});

describe('addServiceToAdminClient — contrato PROD-02F5', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('envía solo los campos del contrato y mapea las respuestas', async () => {
        const { addServiceToAdminClient: real } = await vi.importActual<typeof import('@/lib/admin/client')>('@/lib/admin/client');
        const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(created.data), {
            status: 201, headers: { 'Content-Type': 'application/json' },
        }));
        vi.stubGlobal('fetch', fetchMock);
        const result = await real(7, {
            service_type: 'reception', plan_code: 'reception', complimentary_start: TODAY,
            complimentary_end: SIX_MONTHS, grant_reason: 'Motivo', usage_tier: 'reception_300',
        });
        expect(result.status).toBe('ok');
        const [url, init] = fetchMock.mock.calls[0];
        expect(url).toMatch(/\/api\/v1\/platform-admin\/clients\/7\/services\/$/);
        expect(init.method).toBe('POST');
        expect(JSON.parse(init.body)).toEqual({
            service_type: 'reception', plan_code: 'reception', complimentary_start: TODAY,
            complimentary_end: SIX_MONTHS, grant_reason: 'Motivo', usage_tier: 'reception_300',
        });

        fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
            code: 'incompatible_ai_service', detail: 'x', field: 'service_type',
        }), { status: 409, headers: { 'Content-Type': 'application/json' } }));
        expect(await real(7, {
            service_type: 'reception', plan_code: 'reception', complimentary_start: TODAY,
            complimentary_end: SIX_MONTHS, grant_reason: 'Motivo', custom_included_sessions: 10, usage_tier: 'reception_custom',
        })).toEqual({ status: 'domain_error', httpStatus: 409, error: { code: 'incompatible_ai_service', detail: 'x', field: 'service_type' } });
        expect(JSON.parse(fetchMock.mock.calls[1][1].body).custom_included_sessions).toBe(10);

        fetchMock.mockResolvedValueOnce(new Response('{}', { status: 403, headers: { 'Content-Type': 'application/json' } }));
        expect((await real(7, { service_type: 'reception', plan_code: 'reception', complimentary_start: TODAY, complimentary_end: SIX_MONTHS, grant_reason: 'x' })).status).toBe('forbidden');

        fetchMock.mockRejectedValueOnce(new TypeError('network'));
        expect(await real(7, { service_type: 'reception', plan_code: 'reception', complimentary_start: TODAY, complimentary_end: SIX_MONTHS, grant_reason: 'x' }))
            .toEqual({ status: 'server_error', httpStatus: 0 });
    });
});
