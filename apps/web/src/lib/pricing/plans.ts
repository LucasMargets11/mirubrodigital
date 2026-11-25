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
import type { CanonicalPlanDef, PlanDef } from './types';

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

export const QR_EMPRESARIAL: PlanDef = {
  code: 'menu_qr_empresarial',
  vertical: 'menu_qr',
  name: 'Empresarial',
  priceMonthly: 0,
  priceYearly: 0,
  isCustom: true,
};

// ── QR de Reseñas ─────────────────────────────────────────────────

export const REVIEWS_BASE: PlanDef = {
  code: 'qr_reviews_base',
  vertical: 'qr_reviews',
  name: 'Reseñas Base',
  priceMonthly: 15000,
  priceYearly: 144000,
};

export const REVIEWS_PRO: PlanDef = {
  code: 'qr_reviews_pro',
  vertical: 'qr_reviews',
  name: 'Reseñas Pro',
  priceMonthly: 20000,
  priceYearly: 192000,
};

export const REVIEWS_EMPRESARIAL: PlanDef = {
  code: 'qr_reviews_empresarial',
  vertical: 'qr_reviews',
  name: 'Empresarial',
  priceMonthly: 0,
  priceYearly: 0,
  isCustom: true,
};

// ── Aggregate ─────────────────────────────────────────────────────

export const APPOINTMENTS: PlanDef = {
  code: 'appointments',
  vertical: 'appointments',
  name: 'Turnos',
  priceMonthly: 23000,
  priceYearly: 220800,
  professionalsIncluded: 2,
  secondaryUsersIncluded: 2,
};

export const APPOINTMENTS_PRO: PlanDef = {
  code: 'appointments_pro',
  vertical: 'appointments',
  name: 'Turnos Pro',
  priceMonthly: 28000,
  priceYearly: 268800,
  professionalsIncluded: 5,
  secondaryUsersIncluded: 5,
};

export const APPOINTMENTS_AI: PlanDef<null> = {
  code: 'appointments_ai',
  vertical: 'appointments',
  name: 'Turnos IA Recepcionista',
  priceMonthly: null,
  priceYearly: null,
  pricingMode: 'usage_tier',
  professionalsIncluded: 5,
  secondaryUsersIncluded: 5,
  includesPlans: ['appointments_pro'],
  includedAddons: ['appointments_automations'],
  usageTiers: ['ai_300', 'ai_1500', 'ai_3000', 'custom'],
};

/**
 * PROD-02B: Recepcionista IA, independiente de Turnos. Tarifado por usage tier,
 * sin precio fijo. `secondaryUsersIncluded` es PROVISIONAL (paridad con Turnos IA)
 * hasta su aprobación comercial; no hay profesionales en este servicio.
 */
export const RECEPTION: PlanDef<null> = {
  code: 'reception',
  vertical: 'reception',
  name: 'Recepcionista IA',
  priceMonthly: null,
  priceYearly: null,
  pricingMode: 'usage_tier',
  secondaryUsersIncluded: 5,
  usageTiers: ['reception_300', 'reception_1500', 'reception_3000', 'reception_custom'],
};

export const ALL_PLANS: readonly CanonicalPlanDef[] = [
  GC_STARTER,
  GC_PRO,
  GC_BUSINESS,
  GC_ENTERPRISE,
  QR_LITE,
  QR_PRO,
  QR_PREMIUM,
  QR_EMPRESARIAL,
  REVIEWS_BASE,
  REVIEWS_PRO,
  REVIEWS_EMPRESARIAL,
  APPOINTMENTS,
  APPOINTMENTS_PRO,
  APPOINTMENTS_AI,
  RECEPTION,
];
