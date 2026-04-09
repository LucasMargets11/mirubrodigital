/**
 * Typed selectors for canonical pricing data.
 */
import type { PlanDef, AddonDef, ExtraDef, Vertical, BillingCycle } from './types';
import { ALL_PLANS } from './plans';
import { ALL_ADDONS } from './addons';
import { ALL_EXTRAS } from './extras';

export function getPlan(code: string): PlanDef | undefined {
  return ALL_PLANS.find((p) => p.code === code);
}

export function getPlansForVertical(v: Vertical): PlanDef[] {
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

export function getPlanPrice(plan: PlanDef, cycle: BillingCycle): number {
  return cycle === 'monthly' ? plan.priceMonthly : plan.priceYearly;
}

export function getAddonPrice(addon: AddonDef, cycle: BillingCycle): number {
  return cycle === 'monthly' ? addon.priceMonthly : addon.priceYearly;
}

export function getExtraPrice(extra: ExtraDef, cycle: BillingCycle): number {
  return cycle === 'monthly' ? extra.priceMonthly : extra.priceYearly;
}
