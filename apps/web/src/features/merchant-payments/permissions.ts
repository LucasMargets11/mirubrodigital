import type { Session } from '@/lib/auth/types';

// Conectar/reconectar/desconectar MP es una acción financiera: el backend
// (`IsBusinessOwnerOrAdmin` + `manage_settings`) solo la permite a OWNER/ADMIN.
// Única fuente de esta regla en el frontend (Turnos y Menú/Propinas).
const FINANCIAL_ROLES = new Set(['owner', 'admin']);

type SessionLike = Pick<Session, 'permissions'> & { current: { role: string } };

/** Puede consultar el estado de la conexión (endpoint de status). */
export function canViewMercadoPago(session: SessionLike): boolean {
    return Boolean(session.permissions?.manage_settings);
}

/** Puede conectar, reconectar o desconectar la cuenta MP del Business. */
export function canManageMercadoPago(session: SessionLike): boolean {
    return canViewMercadoPago(session) && FINANCIAL_ROLES.has(session.current.role);
}
