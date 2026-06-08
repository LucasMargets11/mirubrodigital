const SERVICE_ENTRY_ROUTES: Record<string, string> = {
    gestion: '/app/gestion/dashboard',
    restaurante: '/app/resto',
    menu_qr: '/app/carta',
    qr_reviews: '/app/resenas',
};

export function getServiceEntryPath(slug: string): string | undefined {
    return SERVICE_ENTRY_ROUTES[slug];
}

/* ── Centralised display names ─────────────────────────────────────────────
 *
 * Single source of truth for human-friendly labels shown in navigation,
 * billing, plan pages, etc.  Internal codes (qr_reviews, qr_reviews_base…)
 * must NEVER leak to the end-user — always go through these helpers.
 */

/** Service code → product name (e.g. sidebar header, topbar, planes page). */
const SERVICE_DISPLAY_NAMES: Record<string, string> = {
    gestion: 'Gestión Comercial',
    restaurante: 'Restaurante Inteligente',
    menu_qr: 'Menú QR Online',
    menu_qr_visual: 'Menú QR Visual',
    menu_qr_marca: 'Menú QR Marca',
    qr_reviews: 'QR de Reseñas',
};

/** Plan code → user-facing plan name. */
const PLAN_DISPLAY_NAMES: Record<string, string> = {
    // Gestión Comercial
    gestion_start_monthly: 'Starter',
    gestion_pro_monthly: 'Pro',
    gestion_business_monthly: 'Business',
    gestion_start_yearly: 'Starter',
    gestion_pro_yearly: 'Pro',
    gestion_business_yearly: 'Business',
    start: 'Starter',
    starter: 'Starter',
    plus: 'Business',
    pro: 'Pro',
    business: 'Business',
    enterprise: 'Enterprise',
    // Menú QR
    menu_qr: 'Menú QR Online',
    menu_qr_visual: 'Menú QR Visual',
    menu_qr_marca: 'Menú QR Marca',
    menu_qr_lite: 'Lite',
    menu_qr_pro: 'Pro',
    menu_qr_premium: 'Premium',
    // QR de Reseñas
    qr_reviews: 'Reseñas Base',
    qr_reviews_base: 'Reseñas Base',
    qr_reviews_pro: 'Reseñas Pro',
};

/**
 * Returns the human-friendly name for a service code.
 * Falls back to the code itself only as a last resort.
 */
export function serviceDisplayName(code: string): string {
    return SERVICE_DISPLAY_NAMES[code] ?? code;
}

/**
 * Returns the human-friendly name for a plan code.
 * Falls back to the code itself only as a last resort.
 */
export function planDisplayName(code: string | null | undefined): string {
    if (!code) return '—';
    return PLAN_DISPLAY_NAMES[code] ?? code;
}
