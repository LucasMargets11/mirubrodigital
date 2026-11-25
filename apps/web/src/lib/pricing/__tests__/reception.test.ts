import { describe, expect, it } from 'vitest';
import { ALL_USAGE_TIERS, getPlan, getPlanPrice, getPlansForVertical, getProduct } from '..';
import { buildPricingCatalog } from '../export-json';

const TIERS = ['reception_300', 'reception_1500', 'reception_3000', 'reception_custom'];

describe('Recepcionista IA catalog (unpublished, not purchasable; PROD-02B/02E2A)', () => {
  it('is an inactive product of its own vertical', () => {
    expect(getProduct('reception')).toMatchObject({ vertical: 'reception', is_active: false });
    expect(buildPricingCatalog().products.find((p) => p.code === 'reception')?.is_active).toBe(false);
  });

  it('has a single tier-priced plan without fixed price nor professionals', () => {
    expect(getPlansForVertical('reception').map((p) => p.code)).toEqual(['reception']);
    const plan = getPlan('reception')!;
    expect(plan).toMatchObject({
      name: 'Recepcionista IA',
      pricingMode: 'usage_tier',
      priceMonthly: null,
      priceYearly: null,
      usageTiers: TIERS,
    });
    expect(plan.professionalsIncluded).toBeUndefined();
    expect(plan.secondaryUsersIncluded).toBeGreaterThanOrEqual(1);
  });

  it('fixed internal allowances without prices nor overage; custom stays empty', () => {
    const tiers = ALL_USAGE_TIERS.filter((t) => t.planCode === 'reception');
    expect(tiers.map((t) => t.code)).toEqual(TIERS);
    const allowances: Record<string, number> = {
      reception_300: 300,
      reception_1500: 1500,
      reception_3000: 3000,
    };
    for (const tier of tiers) {
      expect(tier).toMatchObject({ billingMode: 'manual', monthlyPrice: null, annualPrice: null });
      expect(tier.extraConversationPrice).toBeNull();
      if (tier.code in allowances) {
        expect(tier).toMatchObject({
          purchaseMode: 'internal',
          includedConversations: allowances[tier.code],
          defaultExtraSpendLimit: 0,
        });
      } else {
        expect(tier).toMatchObject({
          purchaseMode: 'contact_sales',
          includedConversations: null,
          defaultExtraSpendLimit: null,
        });
      }
    }
    const plan = getPlan('reception')!;
    for (const code of [...TIERS, undefined, 'ai_300']) {
      expect(() => getPlanPrice(plan, 'monthly', code)).toThrow('usage tier');
    }
  });

  it('Turnos IA keeps its own tiers', () => {
    expect(getPlan('appointments_ai')?.usageTiers).toEqual(['ai_300', 'ai_1500', 'ai_3000', 'custom']);
    expect(ALL_USAGE_TIERS.filter((t) => t.planCode === 'appointments_ai').map((t) => t.code)).toEqual([
      'ai_300',
      'ai_1500',
      'ai_3000',
      'custom',
    ]);
  });
});
