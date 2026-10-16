import { apiDelete, apiGet } from '@/lib/api/client';

import type { MercadoPagoConnectionStatus, MercadoPagoOAuthContext } from './types';

// Conexión MP por Business (`apps.merchant_payments`), compartida por Menú/Propinas
// y Turnos. Los endpoints conservan el path histórico `/api/v1/menu/mercadopago/`
// (deuda: canonicalizar sin romper el redirect URI registrado en MP).
const BASE = '/api/v1/menu/mercadopago/connect';

export function getMercadoPagoConnectionStatus() {
    return apiGet<MercadoPagoConnectionStatus>(`${BASE}/status/`);
}

export function startMercadoPagoOAuth(context: MercadoPagoOAuthContext = 'menu') {
    return apiGet<{ auth_url: string }>(`${BASE}/start/?context=${context}`);
}

export function disconnectMercadoPago() {
    return apiDelete<{ detail: string }>(`${BASE}/`);
}
