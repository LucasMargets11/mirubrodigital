import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
    getMenuEngagementSettings: vi.fn(),
    updateMenuEngagementSettings: vi.fn(),
    uploadEngagementQRImage: vi.fn(),
    getMercadoPagoConnectionStatus: vi.fn(),
    startMercadoPagoOAuth: vi.fn(),
    disconnectMercadoPago: vi.fn(),
}));

vi.mock('@/features/menu/api', () => api);

import { EngagementSettingsSection } from '@/components/app/engagement-settings-section';
import { canManageMercadoPago } from '@/features/merchant-payments/permissions';

const ENGAGEMENT = {
    tips_enabled: true,
    tips_mode: 'mp_oauth_checkout',
    mp_tip_url: null,
    mp_qr_image_url: null,
    reviews_enabled: false,
    google_place_id: null,
    google_review_url: null,
};

const NOT_CONNECTED = { connected: false, status: null, mp_user_id: null, updated_at: null };
const CONNECTED = { connected: true, status: 'connected', mp_user_id: '123', updated_at: null };
const ERRORED = { connected: false, status: 'error', mp_user_id: '123', updated_at: null };

// Same helper the /app/carta/engagement page uses to build the prop.
function sessionFor(role: string) {
    return { current: { role }, permissions: { manage_settings: role !== 'viewer', view_menu: true } };
}

async function renderAs(role: string, mpStatus: object) {
    api.getMenuEngagementSettings.mockResolvedValue(ENGAGEMENT);
    api.getMercadoPagoConnectionStatus.mockResolvedValue(mpStatus);
    render(<EngagementSettingsSection canManageMercadoPago={canManageMercadoPago(sessionFor(role))} />);
    await screen.findByText('Conexión con Mercado Pago');
}

const ACTIONS = ['Conectar Mercado Pago', 'Reconectar', 'Desconectar'];

describe('Menú/Propinas — Mercado Pago actions by role', () => {
    beforeEach(() => vi.clearAllMocks());

    it.each(['owner', 'admin'])('%s disconnected → sees Conectar', async (role) => {
        await renderAs(role, NOT_CONNECTED);
        expect(screen.getByRole('button', { name: 'Conectar Mercado Pago' })).toBeInTheDocument();
    });

    it.each(['owner', 'admin'])('%s connected → sees Desconectar', async (role) => {
        await renderAs(role, CONNECTED);
        expect(screen.getByRole('button', { name: 'Desconectar' })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Conectar Mercado Pago' })).not.toBeInTheDocument();
    });

    it.each(['owner', 'admin'])('%s with errored connection → sees Reconectar', async (role) => {
        await renderAs(role, ERRORED);
        expect(screen.getByRole('button', { name: 'Reconectar' })).toBeInTheDocument();
    });

    it('manager disconnected → no Conectar', async () => {
        await renderAs('manager', NOT_CONNECTED);
        for (const name of ACTIONS) expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
        expect(screen.getByText(/Solo el dueño o un administrador/)).toBeInTheDocument();
    });

    it('manager connected → sees status but no Desconectar', async () => {
        await renderAs('manager', CONNECTED);
        expect(screen.getByText(/Conectado/)).toBeInTheDocument();
        for (const name of ACTIONS) expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    });

    it('manager with errored connection → sees status but no Reconectar', async () => {
        await renderAs('manager', ERRORED);
        expect(screen.getByText('Error de conexión')).toBeInTheDocument();
        for (const name of ACTIONS) expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    });

    it('viewer → no financial actions', async () => {
        await renderAs('viewer', CONNECTED);
        for (const name of ACTIONS) expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    });

    it('defaults to no actions when the prop is omitted', async () => {
        api.getMenuEngagementSettings.mockResolvedValue(ENGAGEMENT);
        api.getMercadoPagoConnectionStatus.mockResolvedValue(NOT_CONNECTED);
        render(<EngagementSettingsSection />);
        await screen.findByText('Conexión con Mercado Pago');
        for (const name of ACTIONS) expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    });
});

describe('canManageMercadoPago (shared Turnos/Menú rule)', () => {
    it.each([
        ['owner', true, true],
        ['admin', true, true],
        ['manager', true, false],
        ['viewer', false, false],
        ['staff', true, false],
        ['owner', false, false], // sin manage_settings nunca
    ])('%s (manage_settings=%s) → %s', (role, manageSettings, expected) => {
        expect(canManageMercadoPago({ current: { role }, permissions: { manage_settings: manageSettings } })).toBe(expected);
    });
});
