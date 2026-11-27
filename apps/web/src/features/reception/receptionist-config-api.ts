import { apiGet, apiPatch, apiPost } from '@/lib/api/client';

import type { ReceptionistConfigPatch, ReceptionistConfigResponse } from './types';

/**
 * PROD-08B — Un formulario, dos accesos (PROD-03B). Solo cambia el prefijo:
 * el comercio opera sobre su negocio activo; Platform Admin sobre el cliente
 * elegido. El target forma parte de la query key: datos de un negocio nunca
 * se reutilizan para otro.
 */
export type ReceptionistConfigTarget =
    | { kind: 'business'; businessId: number }
    | { kind: 'platform_admin'; businessId: number };

export type ReceptionistConfigAdapter = {
    key: readonly unknown[];
    get: () => Promise<ReceptionistConfigResponse>;
    /** Siempre sin cuerpo: crea un borrador vacío, nunca al abrir. */
    create: () => Promise<ReceptionistConfigResponse>;
    patch: (body: ReceptionistConfigPatch) => Promise<ReceptionistConfigResponse>;
};

function pathFor(target: ReceptionistConfigTarget): string {
    return target.kind === 'platform_admin'
        ? `/api/v1/platform-admin/clients/${target.businessId}/receptionist-config/`
        : '/api/v1/receptionist-config/';
}

/**
 * PROD-08C — El comercio resuelve el negocio por `X-Business-Id` y, sin él,
 * por la cookie `bid`, que `switch-business` reescribe para todas las
 * pestañas. Fijar el header con el negocio que muestra la pantalla evita que
 * una pestaña vieja escriba sobre el negocio elegido en otra. Platform Admin
 * no lo usa: su Business sale solo del id de la ruta.
 */
function optionsFor(target: ReceptionistConfigTarget) {
    return target.kind === 'business' ? { headers: { 'X-Business-Id': String(target.businessId) } } : undefined;
}

export function receptionistConfigAdapter(target: ReceptionistConfigTarget): ReceptionistConfigAdapter {
    const path = pathFor(target);
    const options = optionsFor(target);
    return {
        key: ['reception', 'receptionist-config', target.kind, target.businessId],
        get: () => apiGet<ReceptionistConfigResponse>(path, options),
        create: () => apiPost<ReceptionistConfigResponse>(path, {}, options),
        patch: (body) => apiPatch<ReceptionistConfigResponse>(path, body, options),
    };
}
