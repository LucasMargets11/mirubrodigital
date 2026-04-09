/**
 * Canonical addon definitions — single source of truth.
 *
 * Prices: ARS pesos integers.
 *
 * Sources verified against:
 *   - gestion-comercial-catalog.ts  ADDONS
 *   - menu-qr-catalog.ts           QR_ADDONS
 *   - docs/PRICING_AUDIT_FULL.md   §2
 */
import type { AddonDef } from './types';

// ── Gestión Comercial ─────────────────────────────────────────────

export const ADDON_CRM: AddonDef = {
  code: 'crm',
  vertical: 'commercial',
  name: 'CRM / Gestión de clientes',
  description: 'Historial de compras, segmentación de clientes y saldos pendientes.',
  priceMonthly: 8000,
  priceYearly: 76800,
  availableFor: ['gestion_start'],
  includedIn: ['gestion_pro', 'gestion_business', 'gestion_enterprise'],
};

export const ADDON_INVOICING: AddonDef = {
  code: 'invoicing',
  vertical: 'commercial',
  name: 'Facturación Electrónica',
  description: 'Emisión de facturas fiscales válidas (AFIP, SAT, etc.).',
  priceMonthly: 15000,
  priceYearly: 144000,
  availableFor: ['gestion_start'],
  includedIn: ['gestion_pro', 'gestion_business', 'gestion_enterprise'],
};

// ── Menú QR ───────────────────────────────────────────────────────

export const ADDON_QR_REVIEWS: AddonDef = {
  code: 'menu_qr_addon_reviews',
  vertical: 'menu_qr',
  name: 'Reseñas de Google',
  description: 'CTA de reseñas en carta pública.',
  priceMonthly: 12000,
  priceYearly: 115200,
  availableFor: ['menu_qr_visual'],
  includedIn: ['menu_qr_marca'],
};

export const ADDON_QR_TIPS: AddonDef = {
  code: 'menu_qr_addon_tips',
  vertical: 'menu_qr',
  name: 'Propinas (Mercado Pago)',
  description: 'CTA de propinas en carta pública.',
  priceMonthly: 12000,
  priceYearly: 115200,
  availableFor: ['menu_qr_visual'],
  includedIn: ['menu_qr_marca'],
};

// ── Aggregate ─────────────────────────────────────────────────────

export const ALL_ADDONS: readonly AddonDef[] = [
  ADDON_CRM,
  ADDON_INVOICING,
  ADDON_QR_REVIEWS,
  ADDON_QR_TIPS,
];
