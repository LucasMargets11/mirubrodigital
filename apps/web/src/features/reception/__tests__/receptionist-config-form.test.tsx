import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// PROD-08B: formulario compartido de configuración de Recepcionista IA
// (contrato PROD-03B), montado primero en el comercio.

vi.mock('@/lib/api/client', async (importOriginal) => ({
    ...(await importOriginal<typeof import('@/lib/api/client')>()),
    apiGet: vi.fn(),
    apiPost: vi.fn(),
    apiPatch: vi.fn(),
}));

import { ApiError, apiGet, apiPatch, apiPost } from '@/lib/api/client';

import { receptionistConfigAdapter } from '../receptionist-config-api';
import { UNSAVED_CHANGES_MESSAGE, changedFields, contentOf, ReceptionistConfigForm } from '../receptionist-config-form';
import type { ReceptionistConfig } from '../types';

const getMock = vi.mocked(apiGet);
const postMock = vi.mocked(apiPost);
const patchMock = vi.mocked(apiPatch);

const MERCHANT_PATH = '/api/v1/receptionist-config/';

function config(overrides: Partial<ReceptionistConfig> = {}): ReceptionistConfig {
    return {
        id: 'cfg-1',
        assistant_name: 'Sol',
        business_category: 'Odontología',
        business_description: 'Clínica dental familiar.',
        custom_instructions: '',
        tone: 'warm',
        language: 'es-AR',
        welcome_message: 'Hola, soy Sol.',
        operational_info: '',
        business_hours: '',
        services: [{ name: 'Limpieza', description: 'Profilaxis' }],
        reference_info: '',
        faqs: [],
        handoff_rules: '',
        status: 'draft',
        version: 3,
        missing_for_ready: [],
        created_at: '2026-11-26T10:00:00+00:00',
        updated_at: '2026-11-26T10:00:00+00:00',
        ...overrides,
    };
}

function apiError(status: number, payload: Record<string, unknown>) {
    return new ApiError(String(payload.detail ?? 'error'), status, payload);
}

function wrapper() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    function Wrapper({ children }: { children: ReactNode }) {
        return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    }
    return Wrapper;
}

function renderForm(props: Partial<Parameters<typeof ReceptionistConfigForm>[0]> = {}) {
    const Wrapper = wrapper();
    const allProps = {
        target: { kind: 'business' as const, businessId: 1 },
        businessName: 'Clínica Sol',
        canEdit: true,
        ...props,
    };
    const utils = render(
        <Wrapper>
            <ReceptionistConfigForm {...allProps} />
        </Wrapper>,
    );
    return {
        ...utils,
        rerenderWith: (next: Partial<typeof allProps>) =>
            utils.rerender(
                <Wrapper>
                    <ReceptionistConfigForm {...allProps} {...next} />
                </Wrapper>,
            ),
    };
}

beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
    patchMock.mockReset();
});

afterEach(() => vi.restoreAllMocks());

describe('adaptadores', () => {
    it('comercio y Platform Admin solo difieren en la ruta; la key incluye el negocio', async () => {
        getMock.mockResolvedValue({ config: null });
        postMock.mockResolvedValue({ config: config() });
        patchMock.mockResolvedValue({ config: config() });

        const merchant = receptionistConfigAdapter({ kind: 'business', businessId: 1 });
        const admin = receptionistConfigAdapter({ kind: 'platform_admin', businessId: 7 });
        await merchant.get();
        await admin.get();
        await merchant.create();
        await admin.patch({ assistant_name: 'X', expected_version: 2 });

        expect(getMock).toHaveBeenNthCalledWith(1, MERCHANT_PATH);
        expect(getMock).toHaveBeenNthCalledWith(2, '/api/v1/platform-admin/clients/7/receptionist-config/');
        expect(postMock).toHaveBeenCalledWith(MERCHANT_PATH, {});
        expect(patchMock).toHaveBeenCalledWith('/api/v1/platform-admin/clients/7/receptionist-config/', {
            assistant_name: 'X',
            expected_version: 2,
        });
        expect(merchant.key).not.toEqual(receptionistConfigAdapter({ kind: 'business', businessId: 2 }).key);
        expect(merchant.key).not.toEqual(receptionistConfigAdapter({ kind: 'platform_admin', businessId: 1 }).key);
    });
});

describe('changedFields', () => {
    it('compara listas por contenido y trata la descripción ausente como vacía', () => {
        const server = config({ services: [{ name: 'Limpieza' }] });
        const same = { ...contentOf(server), services: [{ name: 'Limpieza', description: '' }] };
        expect(changedFields(server, same)).toEqual({});

        const edited = { ...contentOf(server), services: [{ name: 'Limpieza', description: 'Nueva' }], tone: 'formal' as const };
        expect(changedFields(server, edited)).toEqual({
            tone: 'formal',
            services: [{ name: 'Limpieza', description: 'Nueva' }],
        });
    });
});

describe('ReceptionistConfigForm', () => {
    it('sin configuración muestra el estado vacío y solo crea al pedirlo', async () => {
        getMock.mockResolvedValue({ config: null });
        postMock.mockResolvedValue({ config: config({ assistant_name: '', missing_for_ready: ['assistant_name'] }) });
        renderForm();

        expect(await screen.findByText('Tu agente todavía no tiene configuración')).toBeInTheDocument();
        expect(screen.getByText('Clínica Sol')).toBeInTheDocument();
        expect(postMock).not.toHaveBeenCalled();

        fireEvent.click(screen.getByRole('button', { name: 'Crear borrador' }));
        expect(await screen.findByText('Borrador')).toBeInTheDocument();
        expect(postMock).toHaveBeenCalledTimes(1);
        expect(postMock).toHaveBeenCalledWith(MERCHANT_PATH, {});
        expect(screen.getByText(/Para marcarla como lista falta: Nombre del asistente/)).toBeInTheDocument();
    });

    it('si el borrador ya existía (409) relee la configuración en vez de reintentar', async () => {
        getMock.mockResolvedValueOnce({ config: null }).mockResolvedValueOnce({ config: config() });
        postMock.mockRejectedValue(apiError(409, { code: 'receptionist_config_exists', detail: 'ya existe' }));
        renderForm();

        fireEvent.click(await screen.findByRole('button', { name: 'Crear borrador' }));
        expect(await screen.findByDisplayValue('Sol')).toBeInTheDocument();
        expect(postMock).toHaveBeenCalledTimes(1);
        expect(getMock).toHaveBeenCalledTimes(2);
    });

    it('guarda solo los campos modificados con expected_version', async () => {
        getMock.mockResolvedValue({ config: config() });
        patchMock.mockResolvedValue({ config: config({ assistant_name: 'Luna', version: 4 }) });
        renderForm();

        const name = await screen.findByLabelText(/Nombre del asistente/);
        expect(name).toHaveAttribute('maxLength', '80');
        expect(screen.getByText('3/80')).toBeInTheDocument();
        fireEvent.change(name, { target: { value: 'Luna' } });
        expect(screen.getByText('Cambios sin guardar')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));
        expect(await screen.findByText('Cambios guardados.')).toBeInTheDocument();
        expect(patchMock).toHaveBeenCalledWith(MERCHANT_PATH, { assistant_name: 'Luna', expected_version: 3 });
        expect(screen.queryByText('Cambios sin guardar')).not.toBeInTheDocument();
    });

    it('volver un valor a su estado original deja el formulario sin cambios', async () => {
        getMock.mockResolvedValue({ config: config() });
        renderForm();

        fireEvent.click(await screen.findByRole('tab', { name: 'Servicios' }));
        const service = screen.getByLabelText('Nombre del servicio 1');
        fireEvent.change(service, { target: { value: 'Blanqueamiento' } });
        expect(screen.getByRole('button', { name: 'Guardar cambios' })).toBeEnabled();
        fireEvent.change(service, { target: { value: 'Limpieza' } });
        expect(screen.getByRole('button', { name: 'Guardar cambios' })).toBeDisabled();
    });

    it('edita servicios y FAQs por filas y envía la lista completa', async () => {
        getMock.mockResolvedValue({ config: config() });
        patchMock.mockResolvedValue({ config: config({ version: 4 }) });
        renderForm();

        fireEvent.click(await screen.findByRole('tab', { name: 'Servicios' }));
        fireEvent.click(screen.getByRole('button', { name: 'Agregar servicio' }));
        fireEvent.change(screen.getByLabelText('Nombre del servicio 2'), { target: { value: 'Ortodoncia' } });
        fireEvent.click(screen.getByRole('button', { name: 'Quitar servicio 1' }));

        fireEvent.click(screen.getByRole('tab', { name: 'Preguntas frecuentes' }));
        fireEvent.click(screen.getByRole('button', { name: 'Agregar pregunta' }));
        fireEvent.change(screen.getByLabelText('Pregunta 1'), { target: { value: '¿Atienden obras sociales?' } });
        fireEvent.change(screen.getByLabelText('Respuesta 1'), { target: { value: 'Sí, OSDE.' } });

        fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));
        await waitFor(() => expect(patchMock).toHaveBeenCalledTimes(1));
        expect(patchMock).toHaveBeenCalledWith(MERCHANT_PATH, {
            services: [{ name: 'Ortodoncia', description: '' }],
            faqs: [{ question: '¿Atienden obras sociales?', answer: 'Sí, OSDE.' }],
            expected_version: 3,
        });
    });

    it('no permite superar el máximo de servicios', async () => {
        const services = Array.from({ length: 30 }, (_, i) => ({ name: `S${i}`, description: '' }));
        getMock.mockResolvedValue({ config: config({ services }) });
        renderForm();

        fireEvent.click(await screen.findByRole('tab', { name: 'Servicios' }));
        expect(screen.getByText(/\(30\/\s*30\)/)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Agregar servicio' })).toBeDisabled();
    });

    it('ante 409 conserva los cambios locales, no reintenta y relee solo a pedido', async () => {
        getMock
            .mockResolvedValueOnce({ config: config() })
            .mockResolvedValueOnce({ config: config({ assistant_name: 'Estela', version: 5 }) });
        patchMock.mockRejectedValue(apiError(409, { code: 'version_conflict', detail: 'cambió', current_version: 5 }));
        renderForm();

        fireEvent.change(await screen.findByLabelText(/Nombre del asistente/), { target: { value: 'Luna' } });
        fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));

        expect(await screen.findByText('Otra persona guardó cambios en esta configuración')).toBeInTheDocument();
        expect(screen.getByText(/versión 5/)).toBeInTheDocument();
        expect(screen.getByLabelText(/Nombre del asistente/)).toHaveValue('Luna');
        expect(screen.getByRole('button', { name: 'Guardar cambios' })).toBeDisabled();
        expect(patchMock).toHaveBeenCalledTimes(1);
        expect(getMock).toHaveBeenCalledTimes(1);

        fireEvent.click(screen.getByRole('button', { name: 'Cargar la versión actual' }));
        await waitFor(() => expect(screen.getByLabelText(/Nombre del asistente/)).toHaveValue('Estela'));
        expect(getMock).toHaveBeenCalledTimes(2);
        expect(screen.queryByText('Otra persona guardó cambios en esta configuración')).not.toBeInTheDocument();
        expect(patchMock).toHaveBeenCalledTimes(1);
    });

    it('muestra errores de validación por campo aunque estén en otra tab', async () => {
        getMock.mockResolvedValue({ config: config() });
        patchMock.mockRejectedValue(
            apiError(400, {
                code: 'validation_error',
                detail: 'Configuración inválida.',
                fields: { services: ['"Limpieza" está repetido.'], assistant_name: ['El texto parece contener una credencial.'] },
            }),
        );
        renderForm();

        fireEvent.change(await screen.findByLabelText(/Nombre del asistente/), { target: { value: 'sk-test' } });
        fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));

        const summary = await screen.findByRole('list', { name: 'Errores de validación' });
        expect(within(summary).getByText(/Servicios: "Limpieza" está repetido\./)).toBeInTheDocument();
        expect(screen.getByRole('tab', { name: /Servicios \(con errores\)/ })).toBeInTheDocument();
        expect(screen.getByRole('tab', { name: /Identidad \(con errores\)/ })).toBeInTheDocument();
        expect(screen.getByLabelText(/Nombre del asistente/)).toHaveAttribute('aria-invalid', 'true');
        // Los cambios locales siguen en pantalla.
        expect(screen.getByLabelText(/Nombre del asistente/)).toHaveValue('sk-test');

        fireEvent.click(within(summary).getByRole('button', { name: /Servicios:/ }));
        expect(screen.getByRole('tab', { name: /Servicios/ })).toHaveAttribute('aria-selected', 'true');
        expect(screen.getAllByText('"Limpieza" está repetido.').length).toBeGreaterThan(0);
    });

    it('marcar como lista exige contenido completo y no se presenta como agente conectado', async () => {
        getMock.mockResolvedValue({ config: config({ missing_for_ready: ['welcome_message', 'services'] }) });
        renderForm();

        expect(await screen.findByText('Borrador')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Marcar como lista' })).toBeDisabled();
        expect(screen.getByText(/falta: Mensaje de bienvenida, Servicios/)).toBeInTheDocument();
        expect(screen.getByText(/No significa que el agente esté\s+conectado/)).toBeInTheDocument();
        expect(screen.queryByText(/conectado$/i)).not.toBeInTheDocument();
    });

    it('cambia de borrador a lista con expected_version', async () => {
        getMock.mockResolvedValue({ config: config() });
        patchMock.mockResolvedValue({ config: config({ status: 'ready', version: 4 }) });
        renderForm();

        fireEvent.click(await screen.findByRole('button', { name: 'Marcar como lista' }));
        expect(await screen.findByText('Configuración lista')).toBeInTheDocument();
        expect(patchMock).toHaveBeenCalledWith(MERCHANT_PATH, { status: 'ready', expected_version: 3 });
    });

    it('con cambios sin guardar no permite cambiar el estado', async () => {
        getMock.mockResolvedValue({ config: config() });
        renderForm();

        fireEvent.change(await screen.findByLabelText(/Rubro/), { target: { value: 'Estética' } });
        expect(screen.getByRole('button', { name: 'Marcar como lista' })).toBeDisabled();
        expect(screen.getByText('Guardá los cambios antes de cambiar el estado.')).toBeInTheDocument();
    });

    it('volver de lista a borrador pide confirmación con su consecuencia', async () => {
        getMock.mockResolvedValue({ config: config({ status: 'ready' }) });
        patchMock.mockResolvedValue({ config: config({ status: 'draft', version: 4 }) });
        renderForm();

        fireEvent.click(await screen.findByRole('button', { name: 'Volver a borrador' }));
        const dialog = screen.getByRole('dialog', { name: '¿Volver a borrador?' });
        expect(within(dialog).getByText(/el agente deja de\s+atender con estos datos/)).toBeInTheDocument();
        fireEvent.click(within(dialog).getByRole('button', { name: 'Cancelar' }));
        expect(patchMock).not.toHaveBeenCalled();

        fireEvent.click(screen.getByRole('button', { name: 'Volver a borrador' }));
        fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Volver a borrador' }));
        expect(await screen.findByText('Borrador')).toBeInTheDocument();
        expect(patchMock).toHaveBeenCalledWith(MERCHANT_PATH, { status: 'draft', expected_version: 3 });
    });

    it('sin permiso de edición queda en solo lectura', async () => {
        getMock.mockResolvedValue({ config: config() });
        renderForm({ canEdit: false });

        expect(await screen.findByLabelText(/Nombre del asistente/)).toBeDisabled();
        expect(screen.queryByRole('button', { name: 'Guardar cambios' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Marcar como lista' })).not.toBeInTheDocument();
        expect(screen.getByText('Solo lectura.')).toBeInTheDocument();
    });

    it('un 403 al leer muestra sin acceso y no ofrece crear', async () => {
        getMock.mockRejectedValue(apiError(403, { detail: 'forbidden' }));
        renderForm();

        expect(await screen.findByText('Sin acceso a la configuración del agente')).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Crear borrador' })).not.toBeInTheDocument();
        expect(getMock).toHaveBeenCalledTimes(1);
    });

    it('con cambios sin guardar avisa antes de salir por un link o recargar', async () => {
        getMock.mockResolvedValue({ config: config() });
        renderForm();
        const link = document.createElement('a');
        link.href = '#inicio';
        link.textContent = 'Inicio';
        document.body.appendChild(link);

        // Sin cambios: navega sin preguntar.
        const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
        await screen.findByLabelText(/Nombre del asistente/);
        expect(fireEvent.click(link)).toBe(true);
        expect(confirmSpy).not.toHaveBeenCalled();

        fireEvent.change(screen.getByLabelText(/Nombre del asistente/), { target: { value: 'Luna' } });
        expect(fireEvent.click(link)).toBe(false);
        expect(confirmSpy).toHaveBeenCalledWith(UNSAVED_CHANGES_MESSAGE);

        const unload = new Event('beforeunload', { cancelable: true });
        window.dispatchEvent(unload);
        expect(unload.defaultPrevented).toBe(true);

        confirmSpy.mockReturnValue(true);
        expect(fireEvent.click(link)).toBe(true);
        link.remove();
    });

    it('al cambiar de negocio no reutiliza formulario, cambios ni datos del anterior', async () => {
        getMock
            .mockResolvedValueOnce({ config: config() })
            .mockResolvedValueOnce({ config: config({ id: 'cfg-2', assistant_name: 'Mar', version: 1 }) });
        patchMock.mockResolvedValue({ config: config({ id: 'cfg-2', assistant_name: 'Mar', business_category: 'Spa', version: 2 }) });
        const view = renderForm();

        fireEvent.change(await screen.findByLabelText(/Nombre del asistente/), { target: { value: 'Luna' } });
        act(() => view.rerenderWith({ target: { kind: 'business', businessId: 2 }, businessName: 'Spa Mar' }));

        expect(await screen.findByDisplayValue('Mar')).toBeInTheDocument();
        expect(screen.getByText('Spa Mar')).toBeInTheDocument();
        expect(screen.queryByText('Clínica Sol')).not.toBeInTheDocument();
        expect(screen.queryByText('Cambios sin guardar')).not.toBeInTheDocument();
        expect(getMock).toHaveBeenCalledTimes(2);

        fireEvent.change(screen.getByLabelText(/Rubro/), { target: { value: 'Spa' } });
        fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));
        await waitFor(() => expect(patchMock).toHaveBeenCalledTimes(1));
        // Versión y campos del negocio nuevo; nada del cambio hecho en el anterior.
        expect(patchMock).toHaveBeenCalledWith(MERCHANT_PATH, { business_category: 'Spa', expected_version: 1 });
    });
});
