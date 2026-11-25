/**
 * Canonical pricing types.
 *
 * ALL prices are in ARS pesos integers.
 *   36000 = $36.000 ARS/mes
 * Do NOT divide by 100. There are no centavos in this layer.
 */

/** Verticals within canonical pricing scope. */
export type Vertical = 'commercial' | 'menu_qr' | 'qr_reviews' | 'appointments' | 'reception';

export type BillingCycle = 'monthly' | 'yearly';

/** Canonical plan definition. */
export interface PlanDef<Price = number> {
  code: string;
  vertical: Vertical;
  name: string;
  /** ARS pesos integers */
  priceMonthly: Price;
  /** ARS pesos integers */
  priceYearly: Price;
  isCustom?: boolean;
  pricingMode?: 'usage_tier';
  professionalsIncluded?: number;
  secondaryUsersIncluded?: number;
  includesPlans?: string[];
  includedAddons?: string[];
  usageTiers?: string[];
}

export type CanonicalPlanDef = PlanDef | PlanDef<null>;

export interface ProductDef {
  code: string;
  vertical: Vertical;
  name: string;
  description: string;
  is_active: boolean;
  order: number;
}

export type UsageTierDef = {
  code: string;
  planCode: 'appointments_ai' | 'reception';
  name: string;
} & (
  | {
      purchaseMode: 'self_service';
      monthlyPrice: number;
      annualPrice: number;
      includedConversations: number;
      extraConversationPrice: number;
      defaultExtraSpendLimit: number;
    }
  | {
      purchaseMode: 'contact_sales';
      billingMode: 'manual';
      monthlyPrice: null;
      annualPrice: null;
      includedConversations: null;
      extraConversationPrice: null;
      defaultExtraSpendLimit: null;
    }
  | {
      /**
       * PROD-02E2A: internal/manual offer (never purchasable) with a fixed
       * included allowance and NO overage: no overage price, spend limit 0.
       */
      purchaseMode: 'internal';
      billingMode: 'manual';
      monthlyPrice: null;
      annualPrice: null;
      includedConversations: number;
      extraConversationPrice: null;
      defaultExtraSpendLimit: 0;
    }
);

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
  quantityMin?: number;
  quantityStep?: number;
}
