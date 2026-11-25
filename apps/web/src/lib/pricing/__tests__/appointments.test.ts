import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { ALL_ADDONS, ALL_EXTRAS, ALL_USAGE_TIERS, getPlan, getPlanPrice, getProduct } from '..';
import { buildPricingCatalog } from '../export-json';

const generatedPath = resolve(
  __dirname,
  '..',
  '..',
  '..',
  '..',
  '..',
  '..',
  'generated',
  'pricing.json',
);

describe('S2 Turnos catalog (unpublished)', () => {
  it.each([
    ['appointments', 23000, 220800, 2],
    ['appointments_pro', 28000, 268800, 5],
  ] as const)('%s prices and included resources', (code, monthly, annual, included) => {
    const plan = getPlan(code)!;
    expect(getPlanPrice(plan, 'monthly')).toBe(monthly);
    expect(getPlanPrice(plan, 'yearly')).toBe(annual);
    expect(annual * 5).toBe(monthly * 48);
    expect(plan.professionalsIncluded).toBe(included);
    expect(plan.secondaryUsersIncluded).toBe(included);
  });

  it.each([
    ['ai_300', 150000, 1440000, 300, 300, 75000],
    ['ai_1500', 275000, 2640000, 1500, 200, 137500],
    ['ai_3000', 385000, 3696000, 3000, 160, 192500],
  ] as const)(
    '%s is the complete IA price, not an incremental surcharge',
    (code, monthly, annual, conversations, overage, cap) => {
      const plan = getPlan('appointments_ai')!;
      const tier = ALL_USAGE_TIERS.find((t) => t.code === code)!;
      expect(getPlanPrice(plan, 'monthly', code)).toBe(monthly);
      expect(getPlanPrice(plan, 'yearly', code)).toBe(annual);
      expect(annual * 5).toBe(monthly * 48);
      expect(tier.includedConversations).toBe(conversations);
      expect(tier.extraConversationPrice).toBe(overage);
      expect(tier.defaultExtraSpendLimit).toBe(cap);
      expect(plan.priceMonthly).toBeNull();
      expect(plan.includesPlans).toEqual(['appointments_pro']);
      expect(plan.includedAddons).toEqual(['appointments_automations']);
    },
  );

  it('has a single logical IA plan and a contact-only custom tier', () => {
    const plan = getPlan('appointments_ai')!;
    expect(plan.usageTiers).toEqual(['ai_300', 'ai_1500', 'ai_3000', 'custom']);
    expect(() => getPlanPrice(plan, 'monthly')).toThrow('usage tier');
    expect(() => getPlanPrice(plan, 'monthly', 'unknown')).toThrow('usage tier');
    expect(() => getPlanPrice(plan, 'monthly', 'custom')).toThrow('usage tier');
    expect(ALL_USAGE_TIERS.find((t) => t.code === 'custom')).toMatchObject({
      purchaseMode: 'contact_sales',
      billingMode: 'manual',
      monthlyPrice: null,
      annualPrice: null,
      extraConversationPrice: null,
    });
    expect(getPlan('appointments_base')).toBeUndefined();
    expect(getPlan('ai_300')).toBeUndefined();
  });

  it('automations are purchasable only in Turnos/Pro and included in IA', () => {
    expect(ALL_ADDONS.find((a) => a.code === 'appointments_automations')).toMatchObject({
      priceMonthly: 8500,
      priceYearly: 81600,
      availableFor: ['appointments', 'appointments_pro'],
      includedIn: ['appointments_ai'],
    });
  });

  it('extra professional is a quantity, not a second fixed addon', () => {
    expect(ALL_EXTRAS.find((e) => e.code === 'appointments_extra_professional')).toMatchObject({
      priceMonthly: 3000,
      priceYearly: 28800,
      quantityMin: 0,
      quantityStep: 1,
      availableFor: ['appointments', 'appointments_pro', 'appointments_ai'],
    });
    expect(ALL_ADDONS.some((a) => a.code === 'appointments_extra_professional')).toBe(false);
  });

  it('keeps the product inactive', () => {
    expect(getProduct('appointments')?.is_active).toBe(false);
    expect(buildPricingCatalog().products.find((p) => p.code === 'appointments')?.is_active).toBe(
      false,
    );
  });
});

describe('shared pricing exporter regression', () => {
  it('preserves products and the existing offers in every other vertical', () => {
    const output = buildPricingCatalog();
    // Turnos and Recepcionista IA (PROD-02B) are covered by their own tests.
    const own = new Set(['appointments', 'reception']);
    const nonTurnos = {
      products: output.products.filter((p) => !own.has(p.vertical)),
      plans: output.plans.filter((p) => !own.has(p.vertical)),
      addons: output.addons.filter((a) => !own.has(a.vertical)),
      extras: output.extras.filter((e) => !own.has(e.vertical)),
    };
    expect(nonTurnos).toMatchSnapshot();
  });

  it('generates valid JSON with all catalog sections, identical to the persisted artifact', () => {
    const output = buildPricingCatalog();
    const generated = JSON.parse(readFileSync(generatedPath, 'utf8'));
    // The generation date is metadata, not pricing semantics.
    expect({ ...generated, version: output.version }).toEqual(output);
    expect(JSON.parse(JSON.stringify(output))).toEqual(output);
    for (const section of ['products', 'plans', 'addons', 'extras', 'usage_tiers'] as const) {
      expect(output[section].length).toBeGreaterThan(0);
    }
  });
});
