/**
 * Catálogo de funcionalidades de Gestión Comercial
 *
 * Single source of truth para la tabla comparativa de planes.
 * Sincronizado con:
 *   - services/api/src/apps/business/entitlements.py
 *   - services/api/src/apps/billing/commercial_plans.py
 *
 * Availability values:
 *   included       → ✅ Incluido en el plan
 *   addon          → ➕ Disponible como add-on
 *   not_included   → — No incluido
 *   custom         → ⭐ Custom / Ilimitado (Enterprise)
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type FeatureAvailability = 'included' | 'addon' | 'not_included' | 'custom';

export type FeatureCategory =
  | 'Productos'
  | 'Inventario'
  | 'Ventas'
  | 'Clientes'
  | 'Facturación'
  | 'Caja'
  | 'Reportes'
  | 'Exportación'
  | 'Tesorería'
  | 'Seguridad'
  | 'Auditoría'
  | 'Multi-sucursal';

export interface FeatureEntry {
  /** Entitlement key — must match backend entitlements.py */
  key: string;
  /** Human-readable title shown in the table */
  title: string;
  /** Short description for tooltip / expanded row */
  description: string;
  /** Grouping category */
  category: FeatureCategory;
  /** Availability per plan */
  availability: {
    start: FeatureAvailability;
    pro: FeatureAvailability;
    business: FeatureAvailability;
    enterprise: FeatureAvailability;
  };
}

export interface PlanLimitsEntry {
  plan: 'start' | 'pro' | 'business' | 'enterprise';
  label: string;
  branches: string;
  users: string;
  isCustom?: boolean;
}

export interface AddonEntry {
  code: string;
  title: string;
  description: string;
  pricing: {
    monthly: string;
    yearly: string;
  };
  /** Plans where this add-on can be purchased */
  availableFor: string[];
  /** Plans where this is already included */
  includedIn: string[];
}

export interface ExtraEntry {
  code: string;
  title: string;
  pricing: {
    monthly: string;
    yearly: string;
  };
  /** Plans that support adding extras */
  availableFor: string[];
}

export interface LegacyPlanEntry {
  legacyCode: string;
  legacyName: string;
  mapsToPlan: 'start' | 'pro' | 'business' | 'enterprise';
  mapsToLabel: string;
}

// ---------------------------------------------------------------------------
// Plan limits
// ---------------------------------------------------------------------------

export const PLAN_LIMITS: PlanLimitsEntry[] = [
  {
    plan: 'start',
    label: 'START',
    branches: '1 sucursal',
    users: '2 usuarios',
  },
  {
    plan: 'pro',
    label: 'PRO',
    branches: 'Hasta 3 sucursales',
    users: '10 usuarios',
  },
  {
    plan: 'business',
    label: 'BUSINESS',
    branches: 'Ilimitadas (5 incluidas)',
    users: '20 usuarios base',
  },
  {
    plan: 'enterprise',
    label: 'ENTERPRISE',
    branches: 'Ilimitadas',
    users: 'Ilimitados',
    isCustom: true,
  },
];

// ---------------------------------------------------------------------------
// Feature catalog — all keys must exist in backend entitlements.py
// ---------------------------------------------------------------------------

export const FEATURE_CATALOG: FeatureEntry[] = [
  // ── Productos ────────────────────────────────────────────────────────────
  {
    key: 'gestion.products',
    title: 'Gestión de productos',
    description: 'Alta, edición y baja de productos con variantes, precios y códigos de barra.',
    category: 'Productos',
    availability: { start: 'included', pro: 'included', business: 'included', enterprise: 'custom' },
  },

  // ── Inventario ───────────────────────────────────────────────────────────
  {
    key: 'gestion.inventory_basic',
    title: 'Inventario básico',
    description: 'Stock en tiempo real, alertas de bajo stock y ajustes manuales.',
    category: 'Inventario',
    availability: { start: 'included', pro: 'included', business: 'included', enterprise: 'custom' },
  },
  {
    key: 'gestion.inventory_advanced',
    title: 'Inventario avanzado',
    description: 'Gestión de lotes, vencimientos, costo promedio ponderado e historial completo.',
    category: 'Inventario',
    availability: { start: 'not_included', pro: 'included', business: 'included', enterprise: 'custom' },
  },

  // ── Ventas ───────────────────────────────────────────────────────────────
  {
    key: 'gestion.sales_basic',
    title: 'Ventas básicas',
    description: 'Punto de venta, tickets de venta y descuentos simples.',
    category: 'Ventas',
    availability: { start: 'included', pro: 'included', business: 'included', enterprise: 'custom' },
  },
  {
    key: 'gestion.sales_advanced',
    title: 'Ventas avanzadas',
    description: 'Listas de precios, descuentos por cliente y condiciones de pago flexibles.',
    category: 'Ventas',
    availability: { start: 'not_included', pro: 'included', business: 'included', enterprise: 'custom' },
  },
  {
    key: 'gestion.quotes',
    title: 'Cotizaciones',
    description: 'Generación de presupuestos en PDF y conversión a venta en un clic.',
    category: 'Ventas',
    availability: { start: 'not_included', pro: 'included', business: 'included', enterprise: 'custom' },
  },

  // ── Clientes ─────────────────────────────────────────────────────────────
  {
    key: 'gestion.customers',
    title: 'CRM / Gestión de clientes',
    description: 'Base de clientes con historial de compras, segmentación y saldos pendientes.',
    category: 'Clientes',
    availability: { start: 'addon', pro: 'included', business: 'included', enterprise: 'custom' },
  },

  // ── Facturación ──────────────────────────────────────────────────────────
  {
    key: 'gestion.invoices',
    title: 'Facturación electrónica',
    description: 'Emisión de facturas fiscales válidas (AFIP, SAT, etc.), gestión de series y timbrado.',
    category: 'Facturación',
    availability: { start: 'addon', pro: 'included', business: 'included', enterprise: 'custom' },
  },

  // ── Caja ─────────────────────────────────────────────────────────────────
  {
    key: 'gestion.cash',
    title: 'Caja / Sesiones de caja',
    description: 'Apertura y cierre de caja, arqueos y movimientos de efectivo.',
    category: 'Caja',
    availability: { start: 'not_included', pro: 'included', business: 'included', enterprise: 'custom' },
  },

  // ── Reportes ─────────────────────────────────────────────────────────────
  {
    key: 'gestion.dashboard_basic',
    title: 'Dashboard básico',
    description: 'Resumen de ventas del día, productos más vendidos y alertas de stock.',
    category: 'Reportes',
    availability: { start: 'included', pro: 'included', business: 'included', enterprise: 'custom' },
  },
  {
    key: 'gestion.reports',
    title: 'Reportes avanzados',
    description: 'Reportes de ventas, rentabilidad, rotación de stock y comparativas por período.',
    category: 'Reportes',
    availability: { start: 'not_included', pro: 'included', business: 'included', enterprise: 'custom' },
  },
  {
    key: 'gestion.consolidated_reports',
    title: 'Reportes consolidados',
    description: 'Reportes unificados de todas las sucursales con drill-down por local.',
    category: 'Reportes',
    availability: { start: 'not_included', pro: 'not_included', business: 'included', enterprise: 'custom' },
  },

  // ── Exportación ──────────────────────────────────────────────────────────
  {
    key: 'gestion.export',
    title: 'Exportación de datos',
    description: 'Descarga de reportes en Excel / CSV para análisis externo.',
    category: 'Exportación',
    availability: { start: 'not_included', pro: 'included', business: 'included', enterprise: 'custom' },
  },

  // ── Tesorería ────────────────────────────────────────────────────────────
  {
    key: 'gestion.treasury',
    title: 'Tesorería / Finanzas',
    description: 'Gestión de cuentas bancarias, conciliación, ingresos y egresos.',
    category: 'Tesorería',
    availability: { start: 'not_included', pro: 'included', business: 'included', enterprise: 'custom' },
  },

  // ── Seguridad ────────────────────────────────────────────────────────────
  {
    key: 'gestion.settings_basic',
    title: 'Configuración comercial básica',
    description: 'Datos del negocio, moneda, impuestos y horarios.',
    category: 'Seguridad',
    availability: { start: 'included', pro: 'included', business: 'included', enterprise: 'custom' },
  },
  {
    key: 'gestion.rbac_full',
    title: 'Control de acceso por roles (RBAC)',
    description: 'Roles y permisos granulares por usuario y módulo.',
    category: 'Seguridad',
    availability: { start: 'not_included', pro: 'included', business: 'included', enterprise: 'custom' },
  },

  // ── Auditoría ────────────────────────────────────────────────────────────
  {
    key: 'gestion.audit',
    title: 'Registro de auditoría',
    description: 'Historial completo de acciones por usuario con timestamps y filtros.',
    category: 'Auditoría',
    availability: { start: 'not_included', pro: 'included', business: 'included', enterprise: 'custom' },
  },

  // ── Multi-sucursal ───────────────────────────────────────────────────────
  {
    key: 'gestion.multi_branch',
    title: 'Gestión multi-sucursal',
    description: 'Panel unificado para operar múltiples locales desde un solo lugar.',
    category: 'Multi-sucursal',
    availability: { start: 'not_included', pro: 'not_included', business: 'included', enterprise: 'custom' },
  },
  {
    key: 'gestion.transfers',
    title: 'Transferencias entre sucursales',
    description: 'Movimiento de stock entre locales con trazabilidad completa.',
    category: 'Multi-sucursal',
    availability: { start: 'not_included', pro: 'not_included', business: 'included', enterprise: 'custom' },
  },
];

// ---------------------------------------------------------------------------
// Add-ons (purchasable for specific plans)
// ---------------------------------------------------------------------------

export const ADDONS: AddonEntry[] = [
  {
    code: 'crm',
    title: 'CRM / Gestión de clientes',
    description: 'Historial de compras, segmentación de clientes y saldos pendientes.',
    pricing: { monthly: '$20/mes', yearly: '$192/año' },
    availableFor: ['start'],
    includedIn: ['pro', 'business', 'enterprise'],
  },
  {
    code: 'invoicing',
    title: 'Facturación Electrónica',
    description: 'Emisión de facturas fiscales válidas (AFIP, SAT, etc.).',
    pricing: { monthly: '$150/mes', yearly: '$1440/año' },
    availableFor: ['start'],
    includedIn: ['pro', 'business', 'enterprise'],
  },
];

// ---------------------------------------------------------------------------
// Extras (applicable to PRO and BUSINESS)
// ---------------------------------------------------------------------------

export const EXTRAS: ExtraEntry[] = [
  {
    code: 'extra_branch',
    title: 'Sucursal adicional',
    pricing: { monthly: '$50/mes', yearly: '$480/año' },
    availableFor: ['pro', 'business'],
  },
  {
    code: 'extra_user',
    title: 'Usuario adicional',
    pricing: { monthly: '$5/mes', yearly: '$48/año' },
    availableFor: ['pro', 'business'],
  },
];

// ---------------------------------------------------------------------------
// Legacy plan mapping
// ---------------------------------------------------------------------------

export const LEGACY_PLANS: LegacyPlanEntry[] = [
  { legacyCode: 'starter', legacyName: 'Starter', mapsToPlan: 'start', mapsToLabel: 'START' },
  { legacyCode: 'pro', legacyName: 'Pro', mapsToPlan: 'pro', mapsToLabel: 'PRO' },
  { legacyCode: 'plus', legacyName: 'Plus', mapsToPlan: 'business', mapsToLabel: 'BUSINESS' },
];

// ---------------------------------------------------------------------------
// Derived helpers
// ---------------------------------------------------------------------------

/** Returns all unique categories in the order they appear in the catalog */
export function getCatalogCategories(): FeatureCategory[] {
  const seen = new Set<FeatureCategory>();
  const result: FeatureCategory[] = [];
  for (const feature of FEATURE_CATALOG) {
    if (!seen.has(feature.category)) {
      seen.add(feature.category);
      result.push(feature.category);
    }
  }
  return result;
}

/** Returns features grouped by category */
export function getFeaturesByCategory(): Map<FeatureCategory, FeatureEntry[]> {
  const map = new Map<FeatureCategory, FeatureEntry[]>();
  for (const feature of FEATURE_CATALOG) {
    const existing = map.get(feature.category) ?? [];
    existing.push(feature);
    map.set(feature.category, existing);
  }
  return map;
}
