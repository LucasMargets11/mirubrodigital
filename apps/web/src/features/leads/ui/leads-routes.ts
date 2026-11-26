/**
 * PROD-02G2 — Contexto de producto del CRM de Leads (una sola implementación
 * para Turnos y Recepcionista IA). Módulo puro: lo usan tanto componentes de
 * servidor (páginas, layout de Turnos) como de cliente.
 *
 * - `basePath`: raíz de las rutas de la bandeja (`/app/turnos/leads` o
 *   `/app/recepcionista/leads`); deep links, "Volver" y CTAs la usan.
 * - `agendaEnabled`: muestra turnos vinculados, propuestas y acciones de
 *   agenda. En Recepcionista sale del flag de sesión `agenda_integration`
 *   (Leads + acceso efectivo a Turnos, `business/context.py`); en Turnos es
 *   siempre `true`. Es UX: las APIs de agenda conservan sus guards.
 * - `product`: solo vocabulario visible ("paciente" en Turnos, "cliente" en
 *   Recepcionista). Nunca cambia estados ni lógica.
 */
export type LeadsProduct = 'appointments' | 'reception';

export type LeadsRouteContext = {
    basePath: string;
    agendaEnabled: boolean;
    product: LeadsProduct;
};

export const TURNOS_LEADS_BASE_PATH = '/app/turnos/leads';
export const RECEPTION_LEADS_BASE_PATH = '/app/recepcionista/leads';

/** Default de todo el CRM: Turnos, para que su comportamiento no cambie. */
export const TURNOS_LEADS_CONTEXT: LeadsRouteContext = {
    basePath: TURNOS_LEADS_BASE_PATH,
    agendaEnabled: true,
    product: 'appointments',
};

/** Cómo se nombra a quien escribe por WhatsApp, según el producto. */
export function contactNoun(product: LeadsProduct): { singular: string; capitalized: string } {
    return product === 'reception'
        ? { singular: 'cliente', capitalized: 'Cliente' }
        : { singular: 'paciente', capitalized: 'Paciente' };
}

/**
 * Adapta textos escritos para Turnos ("paciente") al producto. Solo cambia
 * vocabulario visible; en Turnos devuelve el texto tal cual.
 */
export function personalize(text: string, product: LeadsProduct): string {
    if (product !== 'reception') return text;
    return text.replace(/\bpaciente\b/g, 'cliente').replace(/\bPaciente\b/g, 'Cliente');
}

export function leadDetailHref(basePath: string, leadId: string): string {
    return `${basePath}/${leadId}`;
}

/**
 * Deep link a Leads de Turnos (bookmarks, `action_url` de notificaciones del
 * backend) para un negocio sin Turnos: la ruta equivalente de Recepcionista,
 * o `null` si `pathname` no es de Leads.
 */
export function receptionLeadsPathFor(pathname: string): string | null {
    if (pathname === TURNOS_LEADS_BASE_PATH) return RECEPTION_LEADS_BASE_PATH;
    if (pathname.startsWith(`${TURNOS_LEADS_BASE_PATH}/`)) {
        return `${RECEPTION_LEADS_BASE_PATH}${pathname.slice(TURNOS_LEADS_BASE_PATH.length)}`;
    }
    return null;
}
