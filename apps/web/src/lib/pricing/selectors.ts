/**
 * Typed selectors for canonical pricing data.
 */
import type { CanonicalPlanDef, AddonDef, ExtraDef, Vertical, BillingCycle } from './types';
import { ALL_PLANS } from './plans';
import { ALL_ADDONS } from './addons';
import { ALL_EXTRAS } from './extras';
import { ALL_PRODUCTS } from './products';
import { ALL_USAGE_TIERS } from './usage-tiers';

export function getPlan(code: string): CanonicalPlanDef | undefined {
  return ALL_PLANS.find((p) => p.code === code);
}

export function getPlansForVertical(v: Vertical): CanonicalPlanDef[] {
  return ALL_PLANS.filter((p) => p.vertical === v);
}

export function getAddon(code: string): AddonDef | undefined {
  return ALL_ADDONS.find((a) => a.code === code);
}

export function getAddonsForVertical(v: Vertical): AddonDef[] {
  return ALL_ADDONS.filter((a) => a.vertical === v);
}

export function getExtra(code: string): ExtraDef | undefined {
  return ALL_EXTRAS.find((e) => e.code === code);
}

export function getProduct(code: string) {
  return ALL_PRODUCTS.find((p) => p.code === code);
}

export function getUsageTier(code: string) {
  return ALL_USAGE_TIERS.find((t) => t.code === code);
}

export function getPlanPrice(
  plan: CanonicalPlanDef,
  cycle: BillingCycle,
  usageTier?: string,
): number {
  if (plan.pricingMode === 'usage_tier') {
    const tier = usageTier ? getUsageTier(usageTier) : undefined;
    if (!tier || tier.planCode !== plan.code || tier.purchaseMode !== 'self_service') {
      throw new Error(`${plan.code} requires a self-service usage tier`);
    }
    return cycle === 'monthly' ? tier.monthlyPrice : tier.annualPrice;
  }
  const price = cycle === 'monthly' ? plan.priceMonthly : plan.priceYearly;
  if (price === null) throw new Error(`${plan.code} has no fixed price`);
  return price;
}

export function getAddonPrice(addon: AddonDef, cycle: BillingCycle): number {
  return cycle === 'monthly' ? addon.priceMonthly : addon.priceYearly;
}

export function getExtraPrice(extra: ExtraDef, cycle: BillingCycle): number {
  return cycle === 'monthly' ? extra.priceMonthly : extra.priceYearly;
}
