/**
 * Gating de navegación del app shell para productos acotados (menu_qr,
 * qr_reviews, appointments). Es solo UX: la seguridad real vive en el backend.
 *
 * Slice 7C: la raíz `/app` matchea SOLO exacto. Antes, `/app` + `startsWith`
 * habilitaba cualquier `/app/*` (un Business solo-Turnos entraba a Carta).
 * Las rutas de módulo (`/app/turnos`, `/app/carta`, ...) sí admiten subrutas.
 */

const APP_ROOT = '/app';

// Rutas transversales que cualquier producto acotado usa desde el sidebar o
// redirects del layout (billing, estado de cuenta, soporte).
const COMMON_ALLOWED_PATHS = [
    APP_ROOT,
    '/app/dashboard', // solo redirige a la entrada del servicio
    '/app/servicios',
    '/app/planes',
    '/app/settings',
    '/app/soporte',
    '/app/cuenta',
];

const MENU_QR_ALLOWED_PATHS = [
    ...COMMON_ALLOWED_PATHS,
    '/app/carta',
    // Legacy paths kept for backward-compat during server redirects
    '/app/menu',
    '/app/settings/online-menu',
];

const QR_REVIEWS_ALLOWED_PATHS = [...COMMON_ALLOWED_PATHS, '/app/resenas'];

// `/app/clientes`: Clientes core compartido con Gestión (Turnos CUSTOMER 02).
const APPOINTMENTS_ALLOWED_PATHS = [...COMMON_ALLOWED_PATHS, '/app/turnos', '/app/clientes'];

export function pathMatches(pathname: string, allowed: string): boolean {
    if (pathname === allowed) {
        return true;
    }
    if (allowed === APP_ROOT) {
        return false;
    }
    return pathname.startsWith(`${allowed}/`);
}

/** `true` → la ruta no pertenece al producto actual (mostrar AccessMessage). */
export function isPathRestrictedForService(service: string | null | undefined, pathname: string): boolean {
    if (service === 'menu_qr') {
        return !MENU_QR_ALLOWED_PATHS.some((allowed) => pathMatches(pathname, allowed));
    }
    if (service === 'qr_reviews') {
        return !QR_REVIEWS_ALLOWED_PATHS.some((allowed) => pathMatches(pathname, allowed));
    }
    if (service === 'appointments') {
        return !APPOINTMENTS_ALLOWED_PATHS.some((allowed) => pathMatches(pathname, allowed));
    }
    return false;
}
