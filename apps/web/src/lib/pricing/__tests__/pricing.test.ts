import { describe, it, expect } from 'vitest';
import { ALL_PLANS } from '../plans';
import { ALL_ADDONS } from '../addons';
import { ALL_EXTRAS } from '../extras';
import { getPlan, getPlansForVertical, getAddon, getExtra } from '../selectors';
import { formatPrice } from '../format';

// ── Plan invariants ──────────────────────────────────────────

describe('canonical plans', () => {
  it('contains 9 plans', () => {
    expect(ALL_PLANS).toHaveLength(9);
  });

  it('annual = monthly × 12 × 0.8 for non-custom plans', () => {
    for (const plan of ALL_PLANS) {
      if (plan.isCustom) continue;
      expect(plan.priceYearly).toBe(Math.round(plan.priceMonthly * 12 * 0.8));
    }
  });

  it('every plan has a unique code', () => {
    const codes = ALL_PLANS.map((p) => p.code);
    expect(new Set(codes).size).toBe(codes.length);
  });

  it('prices are positive integers (non-custom)', () => {
    for (const plan of ALL_PLANS) {
      if (plan.isCustom) continue;
      expect(plan.priceMonthly).toBeGreaterThan(0);
      expect(Number.isInteger(plan.priceMonthly)).toBe(true);
      expect(Number.isInteger(plan.priceYearly)).toBe(true);
    }
  });
});

// ── Addon invariants ─────────────────────────────────────────

describe('canonical addons', () => {
  it('contains 4 addons', () => {
    expect(ALL_ADDONS).toHaveLength(4);
  });

  it('annual = monthly × 12 × 0.8', () => {
    for (const addon of ALL_ADDONS) {
      expect(addon.priceYearly).toBe(Math.round(addon.priceMonthly * 12 * 0.8));
    }
  });

  it('every addon has a unique code', () => {
    const codes = ALL_ADDONS.map((a) => a.code);
    expect(new Set(codes).size).toBe(codes.length);
  });
});

// ── Extra invariants ─────────────────────────────────────────

describe('canonical extras', () => {
  it('contains 2 extras', () => {
    expect(ALL_EXTRAS).toHaveLength(2);
  });

  it('annual = monthly × 12 × 0.8', () => {
    for (const extra of ALL_EXTRAS) {
      expect(extra.priceYearly).toBe(Math.round(extra.priceMonthly * 12 * 0.8));
    }
  });
});

// ── Selectors ────────────────────────────────────────────────

describe('selectors', () => {
  it('getPlan returns correct plan', () => {
    const plan = getPlan('gestion_start');
    expect(plan).toBeDefined();
    expect(plan!.priceMonthly).toBe(36000);
  });

  it('getPlan returns undefined for unknown code', () => {
    expect(getPlan('nonexistent')).toBeUndefined();
  });

  it('getPlansForVertical returns only matching vertical', () => {
    const qrPlans = getPlansForVertical('menu_qr');
    expect(qrPlans).toHaveLength(3);
    expect(qrPlans.every((p) => p.vertical === 'menu_qr')).toBe(true);
  });

  it('getAddon returns correct addon', () => {
    const addon = getAddon('crm');
    expect(addon).toBeDefined();
    expect(addon!.priceMonthly).toBe(8000);
  });

  it('getExtra returns correct extra', () => {
    const extra = getExtra('extra_branch');
    expect(extra).toBeDefined();
    expect(extra!.priceMonthly).toBe(12000);
  });
});

// ── Format ───────────────────────────────────────────────────

describe('formatPrice', () => {
  it('formats 36000 as ARS currency string', () => {
    const formatted = formatPrice(36000);
    // Should contain "36.000" (Argentine thousand separator)
    expect(formatted).toContain('36.000');
  });

  it('formats 0 correctly', () => {
    const formatted = formatPrice(0);
    expect(formatted).toContain('0');
  });
});
