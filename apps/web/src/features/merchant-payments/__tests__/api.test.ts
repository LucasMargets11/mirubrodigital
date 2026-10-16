import { beforeEach, describe, expect, it, vi } from 'vitest';

const client = vi.hoisted(() => ({
    apiGet: vi.fn(),
    apiDelete: vi.fn(),
    apiGetBlob: vi.fn(),
    apiPatch: vi.fn(),
    apiPost: vi.fn(),
}));
vi.mock('@/lib/api/client', () => client);

import { disconnectMercadoPago, getMercadoPagoConnectionStatus, startMercadoPagoOAuth } from '@/features/merchant-payments/api';
import * as menuApi from '@/features/menu/api';

describe('merchant-payments api', () => {
    beforeEach(() => vi.clearAllMocks());

    it('starts OAuth with a closed context (appointments / menu default)', () => {
        startMercadoPagoOAuth('appointments');
        expect(client.apiGet).toHaveBeenLastCalledWith('/api/v1/menu/mercadopago/connect/start/?context=appointments');
        startMercadoPagoOAuth();
        expect(client.apiGet).toHaveBeenLastCalledWith('/api/v1/menu/mercadopago/connect/start/?context=menu');
    });

    it('uses the shared legacy status/disconnect endpoints', () => {
        getMercadoPagoConnectionStatus();
        expect(client.apiGet).toHaveBeenLastCalledWith('/api/v1/menu/mercadopago/connect/status/');
        disconnectMercadoPago();
        expect(client.apiDelete).toHaveBeenLastCalledWith('/api/v1/menu/mercadopago/connect/');
    });

    it('Menú re-exports the same functions (no duplicated OAuth client)', () => {
        expect(menuApi.startMercadoPagoOAuth).toBe(startMercadoPagoOAuth);
        expect(menuApi.getMercadoPagoConnectionStatus).toBe(getMercadoPagoConnectionStatus);
        expect(menuApi.disconnectMercadoPago).toBe(disconnectMercadoPago);
    });
});
