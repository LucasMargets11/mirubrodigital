import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// PROD-09C3: «Mi agente» (comercio) muestra el estado de la atención
// automática, sin poder cambiarlo.

vi.mock('@/lib/api/client', async (importOriginal) => ({
    ...(await importOriginal<typeof import('@/lib/api/client')>()),
    apiGet: vi.fn(),
    apiPost: vi.fn(),
    apiPatch: vi.fn(),
}));

import { apiGet, apiPatch } from '@/lib/api/client';

import { ReceptionistConfigForm } from '../receptionist-config-form';
import type { ReceptionistConfig } from '../types';

const getMock = vi.mocked(apiGet);
const patchMock = vi.mocked(apiPatch);

function config(overrides: Partial<ReceptionistConfig> = {}): ReceptionistConfig {
    return {
        id: 'cfg-1', assistant_name: 'Sol', business_category: 'Odontología', business_description: 'Clínica dental.',
        custom_instructions: '', tone: 'warm', language: 'es-AR', welcome_message: 'Hola.', operational_info: '',
        business_hours: '', services: [{ name: 'Limpieza', description: '' }], reference_info: '', faqs: [],
        handoff_rules: '', status: 'ready', automatic_attention_enabled: true, version: 3, missing_for_ready: [],
        created_at: '2026-11-27T10:00:00+00:00', updated_at: '2026-11-27T10:00:00+00:00',
        ...overrides,
    };
}

function renderForm() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    function Wrapper({ children }: { children: ReactNode }) {
        return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    }
    return render(
        <Wrapper>
            <ReceptionistConfigForm target={{ kind: 'business', businessId: 1 }} businessName="Clínica Sol" canEdit />
        </Wrapper>,
    );
}

async function attentionBlock() {
    const heading = await screen.findByRole('heading', { name: 'Atención automática' });
    return heading.closest('div.space-y-1') as HTMLElement;
}

beforeEach(() => {
    getMock.mockReset();
    patchMock.mockReset();
});

describe('Mi agente — atención automática (solo lectura)', () => {
    it.each([
        [true, 'Habilitada'],
        [false, 'Pausada'],
    ])('%s se muestra como «%s», sin interruptor', async (value, label) => {
        getMock.mockResolvedValue({ config: config({ automatic_attention_enabled: value }) });
        renderForm();
        const block = await attentionBlock();
        expect(within(block).getByText(label)).toBeInTheDocument();
        expect(block).toHaveTextContent('La habilita o la pausa el equipo de Mi Rubro.');
        expect(block).toHaveTextContent('Volver a borrador también la pausa; volver a marcarla como lista no la reactiva.');
        expect(block).toHaveTextContent('Habilitada no significa que el agente esté conectado ni respondiendo.');
        expect(screen.queryByRole('switch')).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /Habilitar|Pausar/ })).not.toBeInTheDocument();
    });

    it('sin el campo: estado desconocido, nunca habilitada', async () => {
        const unknown = config();
        delete (unknown as Partial<ReceptionistConfig>).automatic_attention_enabled;
        getMock.mockResolvedValue({ config: unknown });
        renderForm();
        const block = await attentionBlock();
        expect(within(block).getByText('Estado desconocido')).toBeInTheDocument();
        expect(within(block).queryByText('Habilitada')).not.toBeInTheDocument();
        expect(block).toHaveTextContent('No pudimos verificar el estado de la atención automática.');
    });

    it('guardar contenido nunca envía el control de atención', async () => {
        getMock.mockResolvedValue({ config: config() });
        patchMock.mockResolvedValue({ config: config({ assistant_name: 'Sol 2', version: 4 }) });
        renderForm();
        fireEvent.change(await screen.findByDisplayValue('Sol'), { target: { value: 'Sol 2' } });
        fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }));
        await waitFor(() => expect(patchMock).toHaveBeenCalledTimes(1));
        expect(patchMock.mock.calls[0][1]).toEqual({ assistant_name: 'Sol 2', expected_version: 3 });
    });

    it('volver a borrador: avisa que pausa y que «lista» no la reactiva; el estado sigue al backend', async () => {
        getMock.mockResolvedValue({ config: config() });
        patchMock
            .mockResolvedValueOnce({ config: config({ status: 'draft', automatic_attention_enabled: false, version: 4 }) })
            .mockResolvedValueOnce({ config: config({ status: 'ready', automatic_attention_enabled: false, version: 5 }) });
        renderForm();
        expect(within(await attentionBlock()).getByText('Habilitada')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: 'Volver a borrador' }));
        const dialog = await screen.findByRole('dialog');
        expect(dialog).toHaveTextContent('también pausa la atención automática');
        expect(dialog).toHaveTextContent('la reactiva el equipo de Mi Rubro');
        fireEvent.click(within(dialog).getByRole('button', { name: 'Volver a borrador' }));
        await waitFor(async () => expect(within(await attentionBlock()).getByText('Pausada')).toBeInTheDocument());
        fireEvent.click(await screen.findByRole('button', { name: 'Marcar como lista' }));
        await screen.findByText('Configuración lista');
        expect(within(await attentionBlock()).getByText('Pausada')).toBeInTheDocument();
        expect(patchMock.mock.calls[1][1]).toEqual({ status: 'ready', expected_version: 4 });
    });
});
