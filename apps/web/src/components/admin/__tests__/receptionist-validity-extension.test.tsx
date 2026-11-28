import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { AnchorHTMLAttributes } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// PROD-09D2: «Extender vigencia» de la bonificación de Recepcionista IA en la
// sección de consumo del detalle del cliente (Platform Admin, superadmin).

const { refresh } = vi.hoisted(() => ({ refresh: vi.fn() }));

vi.mock('@/lib/api/client', async (importOriginal) => ({
    ...(await importOriginal<typeof import('@/lib/api/client')>()),
    apiGet: vi.fn(),
    apiPost: vi.fn(),
    apiPatch: vi.fn(),
}));
vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh }) }));
vi.mock('next/link', () => ({
    __esModule: true,
    default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
        <a href={href} {...props}>{children}</a>
    ),
}));
vi.mock('@/components/admin/qr-reviews-card', () => ({ QRResenasCard: () => null }));
vi.mock('@/components/admin/receptionist-readiness-section', () => ({ ReceptionistReadinessSection: () => null }));
vi.mock('@/components/admin/admin-whatsapp-connections-section', () => ({ AdminWhatsAppConnectionsSection: () => null }));
vi.mock('@/components/admin/admin-operational-metrics-section', () => ({ AdminOperationalMetricsSection: () => null }));
// El formulario de configuración tiene su propio suite; acá solo habilita el bloque.
vi.mock('@/features/reception/receptionist-config-form', async (importOriginal) => ({
    ...(await importOriginal<typeof import('@/features/reception/receptionist-config-form')>()),
    ReceptionistConfigForm: () => null,
}));

import { ClienteDetailContent } from '@/app/admin/clientes/[clienteId]/cliente-detail-content';
import { extendableReceptionSubscription, extensionFailure } from '@/components/admin/reception-validity-extension';
import type { AdminAIUsageOverview, AdminSubscriptionExtensionResponse } from '@/features/reception/types';
import { addCalendarMonths } from '@/lib/admin/complimentary-period';
import type { AdminClientDetail } from '@/lib/admin/types';
import { ApiError, apiGet, apiPatch, apiPost } from '@/lib/api/client';
import { addDaysToDateString, dateStringFromTimestampAR, todayDateString } from '@/lib/dates';

const getMock = vi.mocked(apiGet);
const postMock = vi.mocked(apiPost);
const patchMock = vi.mocked(apiPatch);

const base = (id: number) => `/api/v1/platform-admin/clients/${id}`;
const DAY = 86_400_000;

// Vencimiento actual: 00:00 de Argentina (03:00Z) dentro de 10 días, como el alta.
const CURRENT_END = addDaysToDateString(todayDateString(), 10);
const CURRENT_END_ISO = `${CURRENT_END}T03:00:00+00:00`;
const DEFAULT_NEW_END = addCalendarMonths(CURRENT_END, 1);

type Sub = NonNullable<AdminAIUsageOverview['source_subscription']>;

function sourceSub(overrides: Partial<Sub> = {}): Sub {
    return {
        id: 'rsub-1', product: 'reception', service_type: 'reception', plan_code: 'reception',
        usage_tier: 'reception_300', status: 'trialing', provider: 'manual', billing_cycle: null,
        complimentary: true, current_period_start: new Date(Date.now() - 3 * DAY).toISOString(),
        current_period_end: CURRENT_END_ISO, grace_until: null, cancel_at_period_end: false, canceled_at: null,
        ...overrides,
    };
}

function usage(sub: Sub | null = sourceSub(), businessId = 7): AdminAIUsageOverview {
    return {
        business_id: businessId, evaluated_at: '2026-11-27T12:00:00+00:00', summary: null,
        source_subscription: sub,
        diagnosis: { code: sub ? 'ok' : 'no_ai_subscription', subscription_id: sub?.id ?? null, candidates: [] },
        scope: 'commercial_authorization_only',
    };
}

function client(id = 7, name = 'Clínica Sol', subscription: AdminClientDetail['subscription'] = null): AdminClientDetail {
    return {
        id, name, slug: `c-${id}`, status: 'trialing', service_type: 'reception', country: 'AR', currency: 'ARS',
        created_at: null, activated_at: null, trial_starts_at: null, trial_ends_at: null, owner: null,
        members: [], member_count: 0, branch_count: 0, subscription, risk_badges: [],
        recent_payments: [], recent_events: [], recent_audit: [], notes: [], billing_profile: null,
        support_summary: {
            total_tickets: 0, open_tickets: 0, resolved_tickets: 0, last_ticket_at: null,
            last_ticket_reference: null, recent_tickets: [],
        },
    };
}

const config = { config: { id: 'cfg', status: 'ready', automatic_attention_enabled: true, version: 3 } };

/** GET por cliente: configuración (habilita el bloque) y consumo. */
function serve(byBusiness: Record<number, AdminAIUsageOverview | (() => AdminAIUsageOverview)>) {
    getMock.mockImplementation(async (path: string) => {
        for (const [id, value] of Object.entries(byBusiness)) {
            if (path === `${base(Number(id))}/receptionist-config/`) return config;
            if (path === `${base(Number(id))}/ai-usage/`) return typeof value === 'function' ? value() : value;
        }
        throw new Error(`unexpected GET ${path}`);
    });
}

function ok(newEnd: string, sub = sourceSub()): AdminSubscriptionExtensionResponse {
    return {
        business: { id: 7, status: 'trialing', service_type: 'reception', default_service: 'reception' },
        subscription: {
            id: sub.id, service_type: 'reception', plan_code: 'reception', usage_tier: sub.usage_tier,
            provider: 'manual', status: 'trialing', current_period_start: sub.current_period_start ?? '',
            current_period_end: `${newEnd}T03:00:00+00:00`,
        },
        custom_policy: null,
        extension: { previous_end: CURRENT_END_ISO, new_end: `${newEnd}T03:00:00+00:00` },
    };
}

const usageCalls = (id = 7) => getMock.mock.calls.filter(([path]) => path === `${base(id)}/ai-usage/`).length;
const extendButton = () => screen.findByRole('button', { name: 'Extender vigencia' });
const dialog = () => screen.getByRole('dialog', { name: 'Extender vigencia' });
const reasonInput = () => within(dialog()).getByLabelText('Motivo') as HTMLTextAreaElement;
const submit = () => fireEvent.click(within(dialog()).getByRole('button', { name: /Extender vigencia|Extendiendo/ }));

async function openModal() {
    fireEvent.click(await extendButton());
    return dialog();
}

/**
 * Busca la celda del calendario retrocediendo meses (el picker abre en el mes
 * sugerido). `null` si el mes anterior está bloqueado por `min` y la celda no
 * se muestra: también prueba que la fecha no se puede elegir.
 */
function reveal(date: string): HTMLButtonElement | null {
    for (let i = 0; i < 3; i += 1) {
        const cell = document.querySelector<HTMLButtonElement>(`[data-date="${date}"]`);
        if (cell) return cell;
        const prev = screen.getByRole('button', { name: 'Mes anterior' });
        if ((prev as HTMLButtonElement).disabled) return null;
        fireEvent.click(prev);
    }
    return document.querySelector<HTMLButtonElement>(`[data-date="${date}"]`);
}

function expectUnselectable(date: string) {
    const cell = reveal(date);
    if (cell) expect(cell).toBeDisabled();
    else expect(screen.getByRole('button', { name: 'Mes anterior' })).toBeDisabled();
}

function renderDetail(props: { canExtendValidity?: boolean; client?: AdminClientDetail } = {}) {
    return render(<ClienteDetailContent client={props.client ?? client()} canExtendValidity={props.canExtendValidity ?? true} />);
}

beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
    patchMock.mockReset();
    refresh.mockReset();
});

describe('PROD-09D2 — Extender vigencia', () => {
    it('plan fijo: muestra comercio, plan y vencimiento; envía solo fecha y motivo a la suscripción de la fuente', async () => {
        serve({ 7: usage() });
        postMock.mockResolvedValue(ok(DEFAULT_NEW_END));
        renderDetail();
        const modal = await openModal();

        expect(within(modal).getByText('Clínica Sol (ID 7)')).toBeInTheDocument();
        expect(within(modal).getByText('Recepcionista IA · Recepcionista 300')).toBeInTheDocument();
        const [y, m, d] = CURRENT_END.split('-');
        expect(within(modal).getByText(`${d}/${m}/${y}`)).toBeInTheDocument();
        expect(within(modal).getByText(/no reinicia el consumo del período, no cambia el cupo contratado y no\s+modifica la atención automática/)).toBeInTheDocument();

        fireEvent.change(reasonInput(), { target: { value: '  Extensión piloto  ' } });
        const before = usageCalls();
        submit();

        await waitFor(() => expect(postMock).toHaveBeenCalledTimes(1));
        expect(postMock).toHaveBeenCalledWith(
            `${base(7)}/subscriptions/rsub-1/extension/`,
            { complimentary_end: DEFAULT_NEW_END, reason: 'Extensión piloto' },
        );
        const [ny, nm, nd] = DEFAULT_NEW_END.split('-');
        expect(await screen.findByText(`Vigencia extendida hasta el ${nd}/${nm}/${ny}.`)).toBeInTheDocument();
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        // Consumo (y checklist, misma query) y detalle comercial del servidor.
        await waitFor(() => expect(usageCalls()).toBeGreaterThan(before));
        expect(refresh).toHaveBeenCalledTimes(1);
        // La atención automática no se toca.
        expect(patchMock).not.toHaveBeenCalled();
    });

    it('plan personalizado: misma acción, rótulo del tier personalizado', async () => {
        serve({ 7: usage(sourceSub({ id: 'rsub-custom', usage_tier: 'reception_custom' })) });
        postMock.mockResolvedValue(ok(DEFAULT_NEW_END));
        renderDetail();
        const modal = await openModal();
        expect(within(modal).getByText('Recepcionista IA · Recepcionista personalizado')).toBeInTheDocument();
        fireEvent.change(reasonInput(), { target: { value: 'Acuerdo' } });
        submit();
        await waitFor(() => expect(postMock).toHaveBeenCalledWith(
            `${base(7)}/subscriptions/rsub-custom/extension/`, { complimentary_end: DEFAULT_NEW_END, reason: 'Acuerdo' },
        ));
    });

    it('operations (sin permiso de superadmin) no ve la acción', async () => {
        serve({ 7: usage() });
        renderDetail({ canExtendValidity: false });
        expect(await screen.findByRole('heading', { name: 'Consumo comercial de IA' })).toBeInTheDocument();
        await waitFor(() => expect(usageCalls()).toBe(1));
        expect(screen.queryByRole('button', { name: 'Extender vigencia' })).not.toBeInTheDocument();
    });

    it('Recepcionista como servicio adicional: usa la suscripción de la fuente, nunca la principal', async () => {
        const main = { id: 'main-gestion' } as AdminClientDetail['subscription'];
        const detail = { ...client(7, 'Ferretería'), service_type: 'gestion', subscription: main };
        serve({ 7: usage(sourceSub({ id: 'rsub-extra' })) });
        postMock.mockResolvedValue(ok(DEFAULT_NEW_END));
        render(<ClienteDetailContent client={detail as AdminClientDetail} canExtendValidity />);
        await openModal();
        fireEvent.change(reasonInput(), { target: { value: 'Extra' } });
        submit();
        await waitFor(() => expect(postMock).toHaveBeenCalledTimes(1));
        expect(postMock.mock.calls[0][0]).toBe(`${base(7)}/subscriptions/rsub-extra/extension/`);
        expect(postMock.mock.calls[0][0]).not.toContain('main-gestion');
    });

    it('suscripciones no extendibles: no se ofrece la acción', async () => {
        const now = Date.now();
        const cases: Array<[string, Sub | null]> = [
            ['sin fuente', null],
            ['Mercado Pago', sourceSub({ provider: 'mercadopago', complimentary: false, status: 'active' })],
            ['no bonificada', sourceSub({ complimentary: false })],
            ['suspendida', sourceSub({ status: 'suspended' })],
            ['cancelada', sourceSub({ status: 'canceled' })],
            ['baja programada', sourceSub({ cancel_at_period_end: true })],
            ['Turnos IA', sourceSub({ service_type: 'appointments', plan_code: 'appointments_ai', usage_tier: 'ai_300' })],
            ['vencida', sourceSub({ current_period_end: new Date(now - DAY).toISOString() })],
            ['sin comenzar', sourceSub({ current_period_start: new Date(now + DAY).toISOString() })],
            ['sin vencimiento', sourceSub({ current_period_end: null })],
        ];
        for (const [name, sub] of cases) {
            expect(extendableReceptionSubscription(usage(sub), now), name).toBeNull();
        }
        expect(extendableReceptionSubscription(usage(), now)?.id).toBe('rsub-1');

        serve({ 7: usage(sourceSub({ status: 'suspended' })) });
        renderDetail();
        await waitFor(() => expect(usageCalls()).toBe(1));
        expect(await screen.findByRole('heading', { name: 'Consumo comercial de IA' })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Extender vigencia' })).not.toBeInTheDocument();
    });

    it('validaciones locales: motivo obligatorio y máximo 255; no envía nada', async () => {
        serve({ 7: usage() });
        renderDetail();
        await openModal();
        submit();
        expect(within(dialog()).getByText('Indicá el motivo de la extensión.')).toBeInTheDocument();
        fireEvent.change(reasonInput(), { target: { value: 'x'.repeat(256) } });
        submit();
        expect(within(dialog()).getByText('Máximo 255 caracteres.')).toBeInTheDocument();
        expect(reasonInput()).toHaveAttribute('maxLength', '255');
        expect(postMock).not.toHaveBeenCalled();
    });

    it('fecha: el día del vencimiento actual no se puede elegir; otra fecha se envía como YYYY-MM-DD sin conversión', async () => {
        serve({ 7: usage() });
        postMock.mockResolvedValue(ok(addDaysToDateString(CURRENT_END, 1)));
        renderDetail();
        await openModal();
        fireEvent.click(within(dialog()).getByRole('button', { name: /Nueva fecha de vencimiento/ }));
        expectUnselectable(CURRENT_END);
        const next = addDaysToDateString(CURRENT_END, 1);
        const cell = reveal(next) as HTMLButtonElement;
        expect(cell).not.toBeDisabled();
        fireEvent.click(cell);
        fireEvent.change(reasonInput(), { target: { value: 'Un día más' } });
        submit();
        await waitFor(() => expect(postMock).toHaveBeenCalledWith(
            `${base(7)}/subscriptions/rsub-1/extension/`, { complimentary_end: next, reason: 'Un día más' },
        ));
    });

    it('zona horaria: el vencimiento se lee en hora de Argentina (sin corrimiento de un día)', () => {
        // 02:30Z del 10/12 = 23:30 del 09/12 en Buenos Aires.
        expect(dateStringFromTimestampAR('2026-12-10T02:30:00Z')).toBe('2026-12-09');
        expect(dateStringFromTimestampAR('2026-12-10T03:00:00+00:00')).toBe('2026-12-10');
        expect(dateStringFromTimestampAR('2026-12-10T00:00:00-03:00')).toBe('2026-12-10');
        expect(dateStringFromTimestampAR(null)).toBeNull();
        expect(dateStringFromTimestampAR('no-date')).toBeNull();
    });

    it('vencimiento a las 23:30 de Argentina: el mismo día no es válido, el siguiente sí', async () => {
        const day = addDaysToDateString(todayDateString(), 12);
        const lateIso = `${addDaysToDateString(day, 1)}T02:30:00Z`; // 23:30 del `day` en AR
        serve({ 7: usage(sourceSub({ current_period_end: lateIso })) });
        renderDetail();
        await openModal();
        fireEvent.click(within(dialog()).getByRole('button', { name: /Nueva fecha de vencimiento/ }));
        expectUnselectable(day);
        expect(reveal(addDaysToDateString(day, 1))).not.toBeDisabled();
    });

    it('cancelar cierra sin enviar', async () => {
        serve({ 7: usage() });
        renderDetail();
        await openModal();
        fireEvent.change(reasonInput(), { target: { value: 'Algo' } });
        fireEvent.click(within(dialog()).getByRole('button', { name: 'Cancelar' }));
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(postMock).not.toHaveBeenCalled();
    });

    it('solicitud en curso: controles deshabilitados y sin doble envío', async () => {
        serve({ 7: usage() });
        let resolve: (value: AdminSubscriptionExtensionResponse) => void = () => undefined;
        postMock.mockReturnValue(new Promise((r) => { resolve = r; }));
        renderDetail();
        await openModal();
        fireEvent.change(reasonInput(), { target: { value: 'Una vez' } });
        submit();
        const sending = await within(dialog()).findByRole('button', { name: 'Extendiendo…' });
        expect(sending).toBeDisabled();
        expect(within(dialog()).getByRole('button', { name: 'Cancelar' })).toBeDisabled();
        expect(reasonInput()).toBeDisabled();
        expect(within(dialog()).getByRole('button', { name: /Nueva fecha de vencimiento/ })).toBeDisabled();
        fireEvent.click(sending);
        submit();
        expect(postMock).toHaveBeenCalledTimes(1);
        // Sin éxito antes de la confirmación del backend.
        expect(screen.queryByText(/Vigencia extendida/)).not.toBeInTheDocument();
        await act(async () => resolve(ok(DEFAULT_NEW_END)));
        expect(await screen.findByText(/Vigencia extendida hasta/)).toBeInTheDocument();
    });

    it('400 de dominio y de forma: mensaje en el campo y datos preservados', async () => {
        serve({ 7: usage() });
        renderDetail();
        await openModal();
        fireEvent.change(reasonInput(), { target: { value: 'Motivo válido' } });

        postMock.mockRejectedValueOnce(new ApiError('x', 400, { code: 'invalid_end', detail: 'x', field: 'complimentary_end' }));
        submit();
        expect(await within(dialog()).findByText('Tiene que ser posterior al vencimiento actual.')).toBeInTheDocument();
        expect(reasonInput().value).toBe('Motivo válido');

        postMock.mockRejectedValueOnce(new ApiError('x', 400, { code: 'invalid_reason', detail: 'x', field: 'reason' }));
        submit();
        expect(await within(dialog()).findByText('Indicá un motivo de 1 a 255 caracteres.')).toBeInTheDocument();

        postMock.mockRejectedValueOnce(new ApiError('x', 400, { complimentary_end: ['Formato de fecha inválido.'] }));
        submit();
        expect(await within(dialog()).findByText('Formato de fecha inválido.')).toBeInTheDocument();
        expect(reasonInput().value).toBe('Motivo válido');
        expect(refresh).not.toHaveBeenCalled();
    });

    it('403: sin permisos, no se cambia nada', async () => {
        serve({ 7: usage() });
        postMock.mockRejectedValueOnce(new ApiError('x', 403, { code: 'unauthorized_provisioning_actor', detail: 'x' }));
        renderDetail();
        await openModal();
        fireEvent.change(reasonInput(), { target: { value: 'Motivo' } });
        submit();
        expect(await within(dialog()).findByText(/Solo un superadmin puede extender la vigencia/)).toBeInTheDocument();
        expect(within(dialog()).queryByRole('button', { name: 'Recargar datos' })).not.toBeInTheDocument();
    });

    it('404/409 por datos desactualizados: mensaje, recarga explícita y sin reintento', async () => {
        let current = usage();
        serve({ 7: () => current });
        postMock.mockRejectedValueOnce(new ApiError('x', 409, { code: 'subscription_suspended', detail: 'x' }));
        renderDetail();
        await openModal();
        fireEvent.change(reasonInput(), { target: { value: 'Motivo' } });
        submit();
        expect(await within(dialog()).findByText(/La suscripción está suspendida; la extensión no la reactiva\./)).toBeInTheDocument();
        expect(postMock).toHaveBeenCalledTimes(1);

        current = usage(sourceSub({ status: 'suspended' }));
        const before = usageCalls();
        fireEvent.click(within(dialog()).getByRole('button', { name: 'Recargar datos' }));
        await waitFor(() => expect(usageCalls()).toBeGreaterThan(before));
        expect(refresh).toHaveBeenCalledTimes(1);
        await waitFor(() => expect(screen.queryByRole('button', { name: 'Extender vigencia' })).not.toBeInTheDocument());
        expect(postMock).toHaveBeenCalledTimes(1);
    });

    it('mapea todos los códigos de dominio de PROD-09D1', () => {
        const err = (status: number, code: string) => new ApiError('x', status, { code, detail: 'x' });
        expect(extensionFailure(err(400, 'invalid_end')).fields?.complimentary_end).toBeTruthy();
        expect(extensionFailure(err(400, 'invalid_reason')).fields?.reason).toBeTruthy();
        for (const [status, code] of [
            [404, 'client_not_found'], [404, 'subscription_not_found'], [409, 'subscription_not_extendable'],
            [409, 'subscription_canceled'], [409, 'subscription_suspended'], [409, 'subscription_not_complimentary'],
            [409, 'cancellation_scheduled'], [409, 'subscription_not_current'], [409, 'custom_policy_not_extendable'],
        ] as const) {
            const failure = extensionFailure(err(status, code));
            expect(failure.reload, code).toBe(true);
            expect(failure.text, code).toMatch(/No se cambió nada/);
        }
        expect(extensionFailure(err(403, 'unauthorized_provisioning_actor')).reload).toBeFalsy();
        expect(extensionFailure(new ApiError('x', 404, undefined)).reload).toBe(true);
        expect(extensionFailure(new Error('network')).text).toMatch(/No pudimos extender la vigencia/);
    });

    it('cambio de cliente: no mezcla estado ni suscripción', async () => {
        serve({
            7: usage(sourceSub({ id: 'rsub-7' })),
            8: usage(sourceSub({ id: 'rsub-8' }), 8),
        });
        postMock.mockResolvedValue(ok(DEFAULT_NEW_END));
        const { rerender } = renderDetail({ client: client(7, 'Clínica Sol') });
        await openModal();
        fireEvent.change(reasonInput(), { target: { value: 'Para Sol' } });

        rerender(<ClienteDetailContent key={8} client={client(8, 'Clínica Luna')} canExtendValidity />);
        await waitFor(() => expect(usageCalls(8)).toBe(1));
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        const modal = await openModal();
        expect(within(modal).getByText('Clínica Luna (ID 8)')).toBeInTheDocument();
        expect(reasonInput().value).toBe('');
        fireEvent.change(reasonInput(), { target: { value: 'Para Luna' } });
        submit();
        await waitFor(() => expect(postMock).toHaveBeenCalledWith(
            `${base(8)}/subscriptions/rsub-8/extension/`, { complimentary_end: DEFAULT_NEW_END, reason: 'Para Luna' },
        ));
    });
});
