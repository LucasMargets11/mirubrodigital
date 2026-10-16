import type { Session } from '@/lib/auth/types';

export type LeadsAccess = 'ok' | 'no_plan' | 'no_permission';

/**
 * Gating de UI de Leads (LEADS 05A). Mismo criterio que el backend:
 * - plan: flag de sesión `leads`, que el backend deriva del entitlement
 *   `appointments.leads` (`business/features.py::ENTITLEMENT_FEATURE_FLAGS`);
 * - rol: permiso efectivo `view_leads` del servicio activo.
 * El producto Turnos lo garantiza el layout de `/app/turnos`. Es solo UX: la
 * API sigue exigiendo entitlement + RBAC.
 */
export function resolveLeadsAccess(session: Pick<Session, 'features' | 'permissions'>): LeadsAccess {
    if (session.features?.leads !== true) {
        return 'no_plan';
    }
    if (session.permissions?.view_leads !== true) {
        return 'no_permission';
    }
    return 'ok';
}
