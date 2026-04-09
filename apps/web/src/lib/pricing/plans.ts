/**
 * Canonical plan definitions — single source of truth.
 *
 * Prices: ARS pesos integers.
 * Annual formula: monthly × 12 × 0.8 (20% discount).
 *
 * Sources verified against:
 *   - gestion-comercial-catalog.ts  GC_PLANS
 *   - menu-qr-catalog.ts           QR_PLANS
 *   - QrReviewsPlanBuilder.tsx      QR_REVIEWS_PLANS (inline)
 *   - docs/PRICING_AUDIT_FULL.md   §2 "Mapa de Precios Oficiales Vigentes"
 */
import type { PlanDef } from './types';

// ── Gestión Comercial ─────────────────────────────────────────────

export const GC_STARTER: PlanDef = {
  code: 'gestion_start',
  vertical: 'commercial',
  name: 'Starter',
  priceMonthly: 36000,
  priceYearly: 345600,
};

export const GC_PRO: PlanDef = {
  code: 'gestion_pro',
  vertical: 'commercial',
  name: 'Pro',
  priceMonthly: 50000,
  priceYearly: 480000,
};

export const GC_BUSINESS: PlanDef = {
  code: 'gestion_business',
  vertical: 'commercial',
  name: 'Business',
  priceMonthly: 75000,
  priceYearly: 720000,
};

export const GC_ENTERPRISE: PlanDef = {
  code: 'gestion_enterprise',
  vertical: 'commercial',
  name: 'Enterprise',
  priceMonthly: 0,
  priceYearly: 0,
  isCustom: true,
};

// ── Menú QR ───────────────────────────────────────────────────────

export const QR_LITE: PlanDef = {
  code: 'menu_qr_basico',
  vertical: 'menu_qr',
  name: 'Lite',
  priceMonthly: 18000,
  priceYearly: 172800,
};

export const QR_PRO: PlanDef = {
  code: 'menu_qr_visual',
  vertical: 'menu_qr',
  name: 'Pro',
  priceMonthly: 30000,
  priceYearly: 288000,
};

export const QR_PREMIUM: PlanDef = {
  code: 'menu_qr_marca',
  vertical: 'menu_qr',
  name: 'Premium',
  priceMonthly: 55000,
  priceYearly: 528000,
};

// ── QR de Reseñas ─────────────────────────────────────────────────

export const REVIEWS_BASE: PlanDef = {
  code: 'qr_reviews_base',
  vertical: 'qr_reviews',
  name: 'QR Reseñas',
  priceMonthly: 25000,
  priceYearly: 240000,
};

export const REVIEWS_PRO: PlanDef = {
  code: 'qr_reviews_pro',
  vertical: 'qr_reviews',
  name: 'Reseñas Pro',
  priceMonthly: 35000,
  priceYearly: 336000,
};

// ── Aggregate ─────────────────────────────────────────────────────

export const ALL_PLANS: readonly PlanDef[] = [
  GC_STARTER,
  GC_PRO,
  GC_BUSINESS,
  GC_ENTERPRISE,
  QR_LITE,
  QR_PRO,
  QR_PREMIUM,
  REVIEWS_BASE,
  REVIEWS_PRO,
];
