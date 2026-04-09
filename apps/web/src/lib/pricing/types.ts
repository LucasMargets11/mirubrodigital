/**
 * Canonical pricing types.
 *
 * ALL prices are in ARS pesos integers.
 *   36000 = $36.000 ARS/mes
 * Do NOT divide by 100. There are no centavos in this layer.
 */

/** Verticals within canonical pricing scope. */
export type Vertical = 'commercial' | 'menu_qr' | 'qr_reviews';

export type BillingCycle = 'monthly' | 'yearly';

/** Canonical plan definition. */
export interface PlanDef {
  code: string;
  vertical: Vertical;
  name: string;
  /** ARS pesos integers */
  priceMonthly: number;
  /** ARS pesos integers */
  priceYearly: number;
  isCustom?: boolean;
}

/** Canonical addon definition. */
export interface AddonDef {
  code: string;
  vertical: Vertical;
  name: string;
  description: string;
  /** ARS pesos integers */
  priceMonthly: number;
  /** ARS pesos integers */
  priceYearly: number;
  /** Plan codes where this addon can be purchased */
  availableFor: string[];
  /** Plan codes where this addon is already included */
  includedIn: string[];
}

/** Canonical extra resource definition (branch, user). */
export interface ExtraDef {
  code: string;
  vertical: Vertical;
  name: string;
  /** ARS pesos integers */
  priceMonthly: number;
  /** ARS pesos integers */
  priceYearly: number;
  /** Plan codes that support this extra */
  availableFor: string[];
}
