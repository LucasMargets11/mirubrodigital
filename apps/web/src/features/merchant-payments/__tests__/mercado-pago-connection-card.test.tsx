import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
    getMercadoPagoConnectionStatus: vi.fn(),
    startMercadoPagoOAuth: vi.fn(),
    disconnectMercadoPago: vi.fn(),
}));

vi.mock('@/features/merchant-payments/api', () => api);

import { MercadoPagoConnectionCard } from '@/features/merchant-payments/mercado-pago-connection-card';

const NOT_CONNECTED = { connected: false, status: null, mp_user_id: null, updated_at: null };
const CONNECTED = { connected: true, status: 'connected', mp_user_id: '123456', updated_at: '2026-09-29T10:00:00Z' };

describe('MercadoPagoConnectionCard (Turnos)', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.restoreAllMocks();
        window.history.replaceState(null, '', '/app/turnos/configuracion');
    });

    it('not connected → shows Conectar Mercado Pago', async () => {
        api.getMercadoPagoConnectionStatus.mockResolvedValue(NOT_CONNECTED);
        render(<MercadoPagoConnectionCard context="appointments" canView canManage />);
        expect(await screen.findByRole('button', { name: 'Conectar Mercado Pago' })).toBeInTheDocument();
        expect(screen.getByText('Conectá Mercado Pago para cobrar señas online.')).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Desconectar' })).not.toBeInTheDocument();
    });

    it('connected → shows state, public account id and Desconectar', async () => {
        api.getMercadoPagoConnectionStatus.mockResolvedValue(CONNECTED);
        render(<MercadoPagoConnectionCard context="appointments" canView canManage />);
        expect(await screen.findByRole('button', { name: 'Desconectar' })).toBeInTheDocument();
        expect(screen.getByText('Conectado')).toBeInTheDocument();
        expect(screen.getByText(/ID de cuenta 123456/)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Conectar Mercado Pago' })).not.toBeInTheDocument();
    });

    it.each(['expired', 'revoked', 'error'])('status %s → asks to reconnect', async (st) => {
        api.getMercadoPagoConnectionStatus.mockResolvedValue({ ...NOT_CONNECTED, status: st, mp_user_id: '1' });
        render(<MercadoPagoConnectionCard context="appointments" canView canManage />);
        expect(await screen.findByRole('button', { name: 'Reconectar' })).toBeInTheDocument();
        expect(screen.getByText('Necesitamos que vuelvas a conectar Mercado Pago.')).toBeInTheDocument();
        expect(screen.queryByText(st)).not.toBeInTheDocument();
    });

    it('click Conectar starts OAuth with the appointments context and navigates to MP', async () => {
        api.getMercadoPagoConnectionStatus.mockResolvedValue(NOT_CONNECTED);
        api.startMercadoPagoOAuth.mockResolvedValue({ auth_url: 'https://auth.mercadopago.com.ar/authorization?state=x' });
        const navigate = vi.fn();
        render(<MercadoPagoConnectionCard context="appointments" canView canManage navigate={navigate} />);
        fireEvent.click(await screen.findByRole('button', { name: 'Conectar Mercado Pago' }));
        await waitFor(() => expect(navigate).toHaveBeenCalledWith('https://auth.mercadopago.com.ar/authorization?state=x'));
        expect(api.startMercadoPagoOAuth).toHaveBeenCalledWith('appointments');
    });

    it('Reconectar also starts OAuth with the appointments context', async () => {
        api.getMercadoPagoConnectionStatus.mockResolvedValue({ ...NOT_CONNECTED, status: 'expired' });
        api.startMercadoPagoOAuth.mockResolvedValue({ auth_url: 'https://auth.mercadopago.com.ar/authorization' });
        const navigate = vi.fn();
        render(<MercadoPagoConnectionCard context="appointments" canView canManage navigate={navigate} />);
        fireEvent.click(await screen.findByRole('button', { name: 'Reconectar' }));
        await waitFor(() => expect(navigate).toHaveBeenCalled());
        expect(api.startMercadoPagoOAuth).toHaveBeenCalledWith('appointments');
    });

    it('failed OAuth start shows a generic error and does not navigate', async () => {
        api.getMercadoPagoConnectionStatus.mockResolvedValue(NOT_CONNECTED);
        api.startMercadoPagoOAuth.mockRejectedValue(new Error('MP OAuth no configurado en este servidor.'));
        const navigate = vi.fn();
        render(<MercadoPagoConnectionCard context="appointments" canView canManage navigate={navigate} />);
        fireEvent.click(await screen.findByRole('button', { name: 'Conectar Mercado Pago' }));
        expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos iniciar la conexión');
        expect(screen.queryByText(/no configurado/)).not.toBeInTheDocument();
        expect(navigate).not.toHaveBeenCalled();
    });

    it('?mp=connected → refreshes status from the server and cleans the URL', async () => {
        window.history.replaceState(null, '', '/app/turnos/configuracion?mp=connected');
        api.getMercadoPagoConnectionStatus.mockResolvedValue(CONNECTED);
        render(<MercadoPagoConnectionCard context="appointments" canView canManage mpReturn="connected" />);
        expect(await screen.findByRole('button', { name: 'Desconectar' })).toBeInTheDocument();
        expect(api.getMercadoPagoConnectionStatus).toHaveBeenCalled();
        expect(screen.getByText('Mercado Pago quedó conectado.')).toBeInTheDocument();
        expect(window.location.search).toBe('');
    });

    it('?mp=error → shows a generic error message', async () => {
        window.history.replaceState(null, '', '/app/turnos/configuracion?mp=error');
        api.getMercadoPagoConnectionStatus.mockResolvedValue(NOT_CONNECTED);
        render(<MercadoPagoConnectionCard context="appointments" canView canManage mpReturn="error" />);
        expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos conectar Mercado Pago. Probá de nuevo.');
        expect(await screen.findByRole('button', { name: 'Conectar Mercado Pago' })).toBeInTheDocument();
        expect(window.location.search).toBe('');
    });

    it('disconnect → re-fetches status and shows No conectado (no stale state)', async () => {
        api.getMercadoPagoConnectionStatus.mockResolvedValueOnce(CONNECTED).mockResolvedValue(NOT_CONNECTED);
        api.disconnectMercadoPago.mockResolvedValue({ detail: 'ok' });
        vi.spyOn(window, 'confirm').mockReturnValue(true);
        render(<MercadoPagoConnectionCard context="appointments" canView canManage />);
        const button = await screen.findByRole('button', { name: 'Desconectar' });
        await act(async () => {
            fireEvent.click(button);
        });
        expect(await screen.findByRole('button', { name: 'Conectar Mercado Pago' })).toBeInTheDocument();
        expect(screen.getByText('No conectado')).toBeInTheDocument();
        expect(screen.queryByText(/123456/)).not.toBeInTheDocument();
        expect(api.disconnectMercadoPago).toHaveBeenCalledTimes(1);
        expect(api.getMercadoPagoConnectionStatus.mock.calls.length).toBeGreaterThanOrEqual(2);
    });

    it('cancelled confirm does not disconnect', async () => {
        api.getMercadoPagoConnectionStatus.mockResolvedValue(CONNECTED);
        vi.spyOn(window, 'confirm').mockReturnValue(false);
        render(<MercadoPagoConnectionCard context="appointments" canView canManage />);
        fireEvent.click(await screen.findByRole('button', { name: 'Desconectar' }));
        expect(api.disconnectMercadoPago).not.toHaveBeenCalled();
    });

    it.each([
        ['connected', CONNECTED, 'Conectado'],
        ['not connected', NOT_CONNECTED, 'Conectá Mercado Pago para cobrar señas online.'],
        ['reconnect', { ...NOT_CONNECTED, status: 'revoked' }, 'Necesitamos que vuelvas a conectar Mercado Pago.'],
    ])('manager (view-only) sees %s state but no financial actions', async (_label, apiStatus, text) => {
        api.getMercadoPagoConnectionStatus.mockResolvedValue(apiStatus);
        render(<MercadoPagoConnectionCard context="appointments" canView canManage={false} />);
        expect(await screen.findByText(text)).toBeInTheDocument();
        expect(screen.getByText(/Solo el dueño o un administrador/)).toBeInTheDocument();
        for (const name of ['Conectar Mercado Pago', 'Reconectar', 'Desconectar']) {
            expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
        }
        expect(api.startMercadoPagoOAuth).not.toHaveBeenCalled();
        expect(api.disconnectMercadoPago).not.toHaveBeenCalled();
    });

    it('manager still gets ?mp=error feedback without actions', async () => {
        api.getMercadoPagoConnectionStatus.mockResolvedValue(NOT_CONNECTED);
        render(<MercadoPagoConnectionCard context="appointments" canView canManage={false} mpReturn="error" />);
        expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos conectar Mercado Pago');
        expect(screen.queryByRole('button', { name: 'Conectar Mercado Pago' })).not.toBeInTheDocument();
    });

    it('viewer/staff (no manage_settings) → no administrative actions and no API calls', () => {
        render(<MercadoPagoConnectionCard context="appointments" canView={false} canManage={false} mpReturn="connected" />);
        expect(screen.getByText(/Solo los administradores/)).toBeInTheDocument();
        for (const name of ['Conectar Mercado Pago', 'Reconectar', 'Desconectar']) {
            expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
        }
        expect(api.getMercadoPagoConnectionStatus).not.toHaveBeenCalled();
        expect(api.startMercadoPagoOAuth).not.toHaveBeenCalled();
    });

    it('never renders tokens even if the API leaked extra fields', async () => {
        api.getMercadoPagoConnectionStatus.mockResolvedValue({
            ...CONNECTED,
            access_token: 'APP_USR-SECRET-ACCESS',
            refresh_token: 'TG-SECRET-REFRESH',
            scope: 'offline_access read write',
            last_error: 'internal stack trace',
        });
        const { container } = render(<MercadoPagoConnectionCard context="appointments" canView canManage />);
        await screen.findByRole('button', { name: 'Desconectar' });
        const text = container.textContent ?? '';
        for (const secret of ['APP_USR-SECRET-ACCESS', 'TG-SECRET-REFRESH', 'offline_access', 'internal stack trace']) {
            expect(text).not.toContain(secret);
        }
    });
});
