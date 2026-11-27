import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { AnchorHTMLAttributes } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// PROD-08C: formulario compartido de PROD-08B en el detalle del cliente de
// Platform Admin, con el adaptador `platform_admin`.

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
// Tarjeta ajena al slice: no debe llamar a la API en estos tests.
vi.mock('@/components/admin/qr-reviews-card', () => ({ QRResenasCard: () => null }));
// PROD-09B: la preparación tiene su propio suite (receptionist-readiness).
vi.mock('@/components/admin/receptionist-readiness-section', () => ({ ReceptionistReadinessSection: () => null }));
// PROD-08D: consumo y métricas tienen su propio suite (receptionist-admin-metrics).
vi.mock('@/components/admin/admin-ai-usage-section', () => ({ AdminAIUsageSection: () => null }));
vi.mock('@/components/admin/admin-operational-metrics-section', () => ({ AdminOperationalMetricsSection: () => null }));
vi.mock('@/components/admin/admin-whatsapp-connections-section', () => ({ AdminWhatsAppConnectionsSection: () => null }));

import { ClienteDetailContent } from '@/app/admin/clientes/[clienteId]/cliente-detail-content';
import type { ReceptionistConfig } from '@/features/reception/types';
import type { AdminClientDetail } from '@/lib/admin/types';
import { ApiError, apiGet, apiPatch, apiPost } from '@/lib/api/client';

const getMock = vi.mocked(apiGet);
const postMock = vi.mocked(apiPost);
const patchMock = vi.mocked(apiPatch);

const pathOf = (id: number) => `/api/v1/platform-admin/clients/${id}/receptionist-config/`;

function client(overrides: Partial<AdminClientDetail> = {}): AdminClientDetail {
    return {
        id: 7,
        name: 'Clínica Sol',
        slug: 'clinica-sol',
        status: 'active',
        service_type: 'reception',
        country: 'AR',
        currency: 'ARS',
        created_at: null,
        activated_at: null,
        trial_starts_at: null,
        trial_ends_at: null,
        owner: null,
        members: [],
        member_count: 0,
        branch_count: 0,
        subscription: null,
        risk_badges: [],
        recent_payments: [],
        recent_events: [],
        recent_audit: [],
        notes: [],
        billing_profile: null,
        support_summary: {
            total_tickets: 0,
            open_tickets: 0,
            resolved_tickets: 0,
            last_ticket_at: null,
            last_ticket_reference: null,
            recent_tickets: [],
        },
        ...overrides,
    };
}

function config(overrides: Partial<ReceptionistConfig> = {}): ReceptionistConfig {
    return {
        id: 'cfg-7',
        assistant_name: 'Sol',
        business_category: 'Odontología',
        business_description: 'Clínica dental.',
        custom_instructions: '',
        tone: 'warm',
        language: 'es-AR',
        welcome_message: 'Hola.',
        operational_info: '',
        business_hours: '',
        services: [{ name: 'Limpieza', description: '' }],
        reference_info: '',
        faqs: [],
        handoff_rules: '',
        status: 'draft',
        version: 2,
        missing_for_ready: [],
        created_at: '2026-11-26T10:00:00+00:00',
        updated_at: '2026-11-26T10:00:00+00:00',
        ...overrides,
    };
}

function apiError(status: number, payload: Record<string, unknown>) {
    return new ApiError(String(payload.detail ?? 'error'), status, payload);
}

const SECTION = 'Recepcionista IA';

beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
    patchMock.mockReset();
});

describe('Platform Admin — Recepcionista IA en el detalle del cliente', () => {
    it('Recepcionista como servicio principal: monta el formulario sobre el cliente de la ruta', async () => {
        getMock.mockResolvedValue({ config: config() });
        render(<ClienteDetailContent client={client()} />);

        expect(await screen.findByRole('heading', { name: SECTION })).toBeInTheDocument();
        expect(screen.getByText('Clínica Sol (ID 7)')).toBeInTheDocument();
        expect(screen.getByDisplayValue('Sol')).toBeInTheDocument();
        expect(screen.getByText(/no significa agente conectado/)).toBeInTheDocument();
        // Solo el id de la ruta; sin X-Business-Id (independiente de `bid`).
        expect(getMock).toHaveBeenCalledTimes(1);
        expect(getMock).toHaveBeenCalledWith(pathOf(7), undefined);
        expect(screen.queryByText(/WhatsApp conectado/i)).not.toBeInTheDocument();
    });

    it('Recepcionista como servicio adicional (principal Gestión) también se muestra', async () => {
        getMock.mockResolvedValue({ config: null });
        render(<ClienteDetailContent client={client({ id: 9, name: 'Ferretería Sur', service_type: 'gestion' })} />);

        expect(await screen.findByRole('heading', { name: SECTION })).toBeInTheDocument();
        expect(screen.getByText('Este cliente todavía no tiene configuración')).toBeInTheDocument();
        expect(getMock).toHaveBeenCalledWith(pathOf(9), undefined);
    });

    it('cliente sin Recepcionista (404 client_not_found): la sección no aparece', async () => {
        getMock.mockRejectedValue(apiError(404, { code: 'client_not_found', detail: 'Cliente no encontrado.' }));
        render(<ClienteDetailContent client={client({ service_type: 'appointments' })} />);

        await waitFor(() => expect(getMock).toHaveBeenCalledTimes(1));
        // El resto del detalle sigue igual.
        expect(screen.getByRole('heading', { name: 'Datos generales' })).toBeInTheDocument();
        await waitFor(() => expect(screen.queryByRole('heading', { name: SECTION })).not.toBeInTheDocument());
        expect(postMock).not.toHaveBeenCalled();
    });

    it.each([
        ['403 de permisos', apiError(403, { detail: 'No tenés permiso.' }), 'Sin acceso a la configuración del agente'],
        ['404 sin código de dominio', apiError(404, { detail: 'Not found.' }), 'No pudimos cargar la configuración'],
        ['500', apiError(500, { detail: 'boom' }), 'No pudimos cargar la configuración'],
        ['error de red', new TypeError('Failed to fetch'), 'No pudimos cargar la configuración'],
    ])('%s no se confunde con ausencia del servicio', async (_label, error, message) => {
        getMock.mockRejectedValue(error);
        render(<ClienteDetailContent client={client()} />);

        expect(await screen.findByRole('heading', { name: SECTION })).toBeInTheDocument();
        expect(screen.getByText(message)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Crear borrador' })).not.toBeInTheDocument();
    });

    it('un 403 explica el permiso de Platform Admin, sin reintentar', async () => {
        getMock.mockRejectedValue(apiError(403, { detail: 'No tenés permiso.' }));
        render(<ClienteDetailContent client={client()} />);

        expect(await screen.findByText(/Tu rol de Platform Admin no permite/)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Reintentar' })).not.toBeInTheDocument();
        expect(getMock).toHaveBeenCalledTimes(1);
    });

    it('crea el borrador solo a pedido y lo edita con expected_version', async () => {
        getMock.mockResolvedValue({ config: null });
        postMock.mockResolvedValue({
            config: config({ assistant_name: '', version: 1, missing_for_ready: ['assistant_name'] }),
        });
        patchMock.mockResolvedValue({ config: config({ assistant_name: 'Luna', version: 2 }) });
        render(<ClienteDetailContent client={client()} />);

        fireEvent.click(await screen.findByRole('button', { name: 'Crear borrador' }));
        expect(await screen.findByText('Borrador')).toBeInTheDocument();
        expect(postMock).toHaveBeenCalledWith(pathOf(7), {}, undefined);

        fireEvent.change(screen.getByLabelText(/Nombre del asistente/), { target: { value: 'Luna' } });
        fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));
        expect(await screen.findByText('Cambios guardados.')).toBeInTheDocument();
        expect(patchMock).toHaveBeenCalledWith(pathOf(7), { assistant_name: 'Luna', expected_version: 1 }, undefined);
    });

    it('ante 409 conserva los cambios y relee solo a pedido', async () => {
        getMock
            .mockResolvedValueOnce({ config: config() })
            .mockResolvedValueOnce({ config: config({ assistant_name: 'Estela', version: 3 }) });
        patchMock.mockRejectedValue(apiError(409, { code: 'version_conflict', detail: 'cambió', current_version: 3 }));
        render(<ClienteDetailContent client={client()} />);

        fireEvent.change(await screen.findByLabelText(/Nombre del asistente/), { target: { value: 'Luna' } });
        fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));
        expect(await screen.findByText('Otra persona guardó cambios en esta configuración')).toBeInTheDocument();
        expect(screen.getByLabelText(/Nombre del asistente/)).toHaveValue('Luna');
        expect(patchMock).toHaveBeenCalledTimes(1);

        fireEvent.click(screen.getByRole('button', { name: 'Cargar la versión actual' }));
        await waitFor(() => expect(screen.getByLabelText(/Nombre del asistente/)).toHaveValue('Estela'));
        expect(getMock).toHaveBeenNthCalledWith(2, pathOf(7), undefined);
    });

    it('validaciones por campo del backend se muestran en el formulario compartido', async () => {
        getMock.mockResolvedValue({ config: config() });
        patchMock.mockRejectedValue(
            apiError(400, { code: 'validation_error', detail: 'Configuración inválida.', fields: { faqs: ['Cada pregunta frecuente requiere una respuesta.'] } }),
        );
        render(<ClienteDetailContent client={client()} />);

        fireEvent.change(await screen.findByLabelText(/Rubro/), { target: { value: 'Estética' } });
        fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));
        expect(await screen.findByRole('tab', { name: /Preguntas frecuentes \(con errores\)/ })).toBeInTheDocument();
    });

    it('volver de lista a borrador usa el modal del formulario compartido', async () => {
        getMock.mockResolvedValue({ config: config({ status: 'ready' }) });
        patchMock.mockResolvedValue({ config: config({ status: 'draft', version: 3 }) });
        render(<ClienteDetailContent client={client()} />);

        fireEvent.click(await screen.findByRole('button', { name: 'Volver a borrador' }));
        const dialog = screen.getByRole('dialog', { name: '¿Volver a borrador?' });
        fireEvent.click(within(dialog).getByRole('button', { name: 'Volver a borrador' }));
        expect(await screen.findByText('Borrador')).toBeInTheDocument();
        expect(patchMock).toHaveBeenCalledWith(pathOf(7), { status: 'draft', expected_version: 2 }, undefined);
    });

    it('al pasar a otro cliente no arrastra datos, cambios ni versión', async () => {
        getMock.mockImplementation(async (path: string) =>
            path === pathOf(7)
                ? { config: config() }
                : { config: config({ id: 'cfg-8', assistant_name: 'Mar', version: 5 }) },
        );
        patchMock.mockResolvedValue({
            config: config({ id: 'cfg-8', assistant_name: 'Mar', business_category: 'Spa', version: 6 }),
        });
        const view = render(<ClienteDetailContent client={client()} />);

        fireEvent.change(await screen.findByLabelText(/Nombre del asistente/), { target: { value: 'Luna' } });
        view.rerender(<ClienteDetailContent client={client({ id: 8, name: 'Spa Mar' })} />);

        expect(await screen.findByDisplayValue('Mar')).toBeInTheDocument();
        expect(screen.getByText('Spa Mar (ID 8)')).toBeInTheDocument();
        expect(screen.queryByText('Clínica Sol (ID 7)')).not.toBeInTheDocument();
        expect(screen.queryByText('Cambios sin guardar')).not.toBeInTheDocument();

        fireEvent.change(screen.getByLabelText(/Rubro/), { target: { value: 'Spa' } });
        fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));
        await waitFor(() => expect(patchMock).toHaveBeenCalledTimes(1));
        expect(patchMock).toHaveBeenCalledWith(pathOf(8), { business_category: 'Spa', expected_version: 5 }, undefined);
    });

    it('la cookie bid del comercio no cambia el cliente administrado', async () => {
        document.cookie = 'bid=99; path=/';
        getMock.mockResolvedValue({ config: config() });
        patchMock.mockResolvedValue({ config: config({ assistant_name: 'Luna', version: 3 }) });
        render(<ClienteDetailContent client={client()} />);

        fireEvent.change(await screen.findByLabelText(/Nombre del asistente/), { target: { value: 'Luna' } });
        fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));
        await waitFor(() => expect(patchMock).toHaveBeenCalledTimes(1));
        for (const call of [...getMock.mock.calls, ...patchMock.mock.calls]) {
            expect(call[0]).toBe(pathOf(7));
            expect(call[call.length - 1]).toBeUndefined();
            expect(JSON.stringify(call)).not.toContain('99');
        }
        document.cookie = 'bid=; path=/; max-age=0';
    });
});
