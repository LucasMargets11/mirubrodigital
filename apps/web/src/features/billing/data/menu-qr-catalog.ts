/**
 * Catálogo de funcionalidades de Menú QR Online
 *
 * Single source of truth para la tabla comparativa de planes (Lite / Pro / Premium).
 * Sincronizado con:
 *   - services/api/src/apps/business/features.py  (PLAN_FEATURES)
 *   - services/api/src/apps/menu/qr_entitlements.py  (resolve_menu_qr_flags)
 *
 * Availability values:
 *   included       → ✅ Incluido en el plan
 *   addon          → ➕ Disponible como add-on
 *   not_included   → — No incluido
 *   conditional    → ⚡ Incluido si elegís este módulo en PRO, o como add-on
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

import type { FeatureAvailability } from './gestion-comercial-catalog';

/** Extiende FeatureAvailability con valor especial para PRO seleccionable */
export type QrFeatureAvailability = FeatureAvailability | 'conditional';

export type QrFeatureCategory =
  | 'Carta Digital'
  | 'Branding'
  | 'Imágenes'
  | 'Analítica'
  | 'Engagement'
  | 'Infraestructura';

export interface QrFeatureEntry {
  /** Feature key — debe coincidir con features.py */
  key: string;
  title: string;
  description: string;
  category: QrFeatureCategory;
  availability: {
    lite: QrFeatureAvailability;
    pro: QrFeatureAvailability;
    premium: QrFeatureAvailability;
  };
  /** Tooltip adicional para el valor "conditional" en PRO */
  conditionalNote?: string;
}

export interface QrPlanEntry {
  plan: 'lite' | 'pro' | 'premium';
  label: string;
  badge?: string;
  priceMonthly: number;
  priceYearly: number;
  description: string;
  ctaLabel: string;
  isRecommended?: boolean;
}

export interface QrAddonEntry {
  code: string;
  title: string;
  description: string;
  pricing: {
    monthly: string;
    yearly: string;
  };
  /** Solo PRO puede comprar add-ons */
  availableFor: string[];
  /** Premium incluye ambos sin add-ons */
  includedIn: string[];
  /** La key de feature que activa este add-on */
  featureKey: string;
}

// ---------------------------------------------------------------------------
// Plan definitions
// ---------------------------------------------------------------------------

export const QR_PLANS: QrPlanEntry[] = [
  {
    plan: 'lite',
    label: 'Lite',
    priceMonthly: 1490,
    priceYearly: 14304,
    description: 'Carta digital básica con branding. Ideal para empezar.',
    ctaLabel: 'Empezar con Lite',
  },
  {
    plan: 'pro',
    label: 'Pro',
    badge: 'Recomendado',
    priceMonthly: 2990,
    priceYearly: 28704,
    description: 'Imágenes, analítica avanzada y 1 módulo de engagement a elección.',
    ctaLabel: 'Elegir Pro',
    isRecommended: true,
  },
  {
    plan: 'premium',
    label: 'Premium',
    priceMonthly: 4990,
    priceYearly: 47904,
    description: 'Todo incluido: reseñas, propinas, imágenes, dominio y multi-sucursal.',
    ctaLabel: 'Ir a Premium',
  },
];

// ---------------------------------------------------------------------------
// Add-ons (solo para plan PRO)
// ---------------------------------------------------------------------------

export const QR_ADDONS: QrAddonEntry[] = [
  {
    code: 'menu_qr_addon_reviews',
    title: 'Reseñas de Google',
    description: 'Agrega el CTA de reseñas si elegiste Propina como módulo incluido.',
    pricing: { monthly: '$990/mes', yearly: '$9504/año' },
    availableFor: ['pro'],
    includedIn: ['premium'],
    featureKey: 'menu_qr_reviews',
  },
  {
    code: 'menu_qr_addon_tips',
    title: 'Propinas (Mercado Pago)',
    description: 'Agrega el CTA de propinas si elegiste Reseñas como módulo incluido.',
    pricing: { monthly: '$990/mes', yearly: '$9504/año' },
    availableFor: ['pro'],
    includedIn: ['premium'],
    featureKey: 'menu_qr_tips',
  },
];

// ---------------------------------------------------------------------------
// Feature catalog
// ---------------------------------------------------------------------------

export const QR_FEATURE_CATALOG: QrFeatureEntry[] = [
  // ── Carta Digital ────────────────────────────────────────────────────────
  {
    key: 'menu_builder',
    title: 'Editor de carta digital',
    description: 'ABM de categorías y productos con posición, descripción, tags y precios.',
    category: 'Carta Digital',
    availability: { lite: 'included', pro: 'included', premium: 'included' },
  },
  {
    key: 'public_menu',
    title: 'URL pública de la carta',
    description: 'Link y QR único para compartir con tus clientes. Acceso desde cualquier dispositivo.',
    category: 'Carta Digital',
    availability: { lite: 'included', pro: 'included', premium: 'included' },
  },
  {
    key: 'menu_qr_tools',
    title: 'Herramientas QR',
    description: 'Generación de código QR en alta resolución, listo para imprimir.',
    category: 'Carta Digital',
    availability: { lite: 'included', pro: 'included', premium: 'included' },
  },

  // ── Branding ─────────────────────────────────────────────────────────────
  {
    key: 'menu_branding',
    title: 'Branding de la carta',
    description: 'Logo, paleta de colores, fuentes y nombre del local personalizados.',
    category: 'Branding',
    availability: { lite: 'included', pro: 'included', premium: 'included' },
  },
  {
    key: 'menu_custom_domain',
    title: 'Dominio personalizado',
    description: 'Mostrá tu carta en tu propio dominio (ej: carta.turestaurante.com).',
    category: 'Branding',
    availability: { lite: 'not_included', pro: 'not_included', premium: 'included' },
  },

  // ── Imágenes ─────────────────────────────────────────────────────────────
  {
    key: 'menu_item_images',
    title: 'Fotos por producto',
    description: 'Subí una imagen para cada plato o producto de la carta.',
    category: 'Imágenes',
    availability: { lite: 'not_included', pro: 'included', premium: 'included' },
  },

  // ── Analítica ────────────────────────────────────────────────────────────
  {
    key: 'analytics_basic',
    title: 'Analítica básica',
    description: 'Vistas de la carta, tiempo promedio y productos más visitados.',
    category: 'Analítica',
    availability: { lite: 'included', pro: 'included', premium: 'included' },
  },
  {
    key: 'analytics_advanced',
    title: 'Analítica avanzada',
    description: 'Embudos de engagement, tasas de conversión reseña/propina y reportes exportables.',
    category: 'Analítica',
    availability: { lite: 'not_included', pro: 'included', premium: 'included' },
  },

  // ── Engagement ───────────────────────────────────────────────────────────
  {
    key: 'menu_qr_reviews',
    title: 'Reseñas de Google',
    description: 'CTA visible en la carta pública para que tus clientes dejen una reseña en Google.',
    category: 'Engagement',
    availability: { lite: 'not_included', pro: 'conditional', premium: 'included' },
    conditionalNote: 'Incluido si elegís "Reseñas" como módulo en PRO, o disponible como add-on.',
  },
  {
    key: 'menu_qr_tips',
    title: 'Propinas (MP link / QR)',
    description: 'Botón de propina con link de Mercado Pago o imagen QR, visible en la carta pública.',
    category: 'Engagement',
    availability: { lite: 'not_included', pro: 'conditional', premium: 'included' },
    conditionalNote: 'Incluido si elegís "Propina" como módulo en PRO, o disponible como add-on.',
  },
  {
    key: 'menu_qr_tips_pro',
    title: 'Propinas dinámicas (MP OAuth)',
    description: 'El cliente elige el monto de propina en la carta — integración avanzada con Mercado Pago.',
    category: 'Engagement',
    availability: { lite: 'not_included', pro: 'not_included', premium: 'included' },
  },

  // ── Infraestructura ──────────────────────────────────────────────────────
  {
    key: 'multi_branch',
    title: 'Multi-sucursal',
    description: 'Cada sucursal puede tener su propia carta, QR y configuración de branding.',
    category: 'Infraestructura',
    availability: { lite: 'not_included', pro: 'not_included', premium: 'included' },
  },
];

// ---------------------------------------------------------------------------
// Pro modules (selectable when plan = PRO)
// ---------------------------------------------------------------------------

export type ProModule = 'reviews' | 'tips';

export interface ProModuleOption {
  value: ProModule;
  label: string;
  description: string;
  featureKey: string;
  addonCode: string;
}

export const PRO_MODULE_OPTIONS: ProModuleOption[] = [
  {
    value: 'reviews',
    label: 'Reseñas de Google',
    description: 'Activa el CTA de reseñas en tu carta pública. El add-on Propina queda disponible.',
    featureKey: 'menu_qr_reviews',
    addonCode: 'menu_qr_addon_tips',
  },
  {
    value: 'tips',
    label: 'Propinas (Mercado Pago)',
    description: 'Activa el botón de propinas en tu carta pública. El add-on Reseñas queda disponible.',
    featureKey: 'menu_qr_tips',
    addonCode: 'menu_qr_addon_reviews',
  },
];

// ---------------------------------------------------------------------------
// Derived helpers
// ---------------------------------------------------------------------------

/** Returns unique categories in appearance order */
export function getQrCatalogCategories(): QrFeatureCategory[] {
  const seen = new Set<QrFeatureCategory>();
  const result: QrFeatureCategory[] = [];
  for (const feature of QR_FEATURE_CATALOG) {
    if (!seen.has(feature.category)) {
      seen.add(feature.category);
      result.push(feature.category);
    }
  }
  return result;
}

/** ARS prices formatted */
export function formatArsPrice(cents: number): string {
  return new Intl.NumberFormat('es-AR', {
    style: 'currency',
    currency: 'ARS',
    maximumFractionDigits: 0,
  }).format(cents);
}
