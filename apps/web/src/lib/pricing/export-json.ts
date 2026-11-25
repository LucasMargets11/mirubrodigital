/**
 * Generates generated/pricing.json from the canonical TS definitions.
 *
 * Usage:
 *   npx tsx apps/web/src/lib/pricing/export-json.ts
 *
 * Output:
 *   generated/pricing.json  (monorepo root)
 */
import * as fs from 'node:fs';
import * as path from 'node:path';

import { ALL_PLANS } from './plans';
import { ALL_ADDONS } from './addons';
import { ALL_EXTRAS } from './extras';
import { ALL_PRODUCTS } from './products';
import { ALL_USAGE_TIERS } from './usage-tiers';

export function buildPricingCatalog() {
  return {
    version: new Date().toISOString().slice(0, 10),
    unit: 'ARS_pesos_integer',
    products: ALL_PRODUCTS.map((p) => ({ ...p })),
    plans: ALL_PLANS.map((p) => ({
      code: p.code,
      vertical: p.vertical,
      name: p.name,
      price_monthly: p.priceMonthly,
      price_yearly: p.priceYearly,
      is_custom: p.isCustom ?? false,
      ...(p.pricingMode && { pricing_mode: p.pricingMode }),
      ...(p.professionalsIncluded !== undefined && {
        professionals_included: p.professionalsIncluded,
      }),
      ...(p.secondaryUsersIncluded !== undefined && {
        secondary_users_included: p.secondaryUsersIncluded,
      }),
      ...(p.includesPlans && { includes_plans: p.includesPlans }),
      ...(p.includedAddons && { included_addons: p.includedAddons }),
      ...(p.usageTiers && { usage_tiers: p.usageTiers }),
    })),
    addons: ALL_ADDONS.map((a) => ({
      code: a.code,
      vertical: a.vertical,
      name: a.name,
      description: a.description,
      price_monthly: a.priceMonthly,
      price_yearly: a.priceYearly,
      available_for: a.availableFor,
      included_in: a.includedIn,
    })),
    extras: ALL_EXTRAS.map((e) => ({
      code: e.code,
      vertical: e.vertical,
      name: e.name,
      price_monthly: e.priceMonthly,
      price_yearly: e.priceYearly,
      available_for: e.availableFor,
      ...(e.quantityMin !== undefined && { quantity_min: e.quantityMin }),
      ...(e.quantityStep !== undefined && { quantity_step: e.quantityStep }),
    })),
    usage_tiers: ALL_USAGE_TIERS.map((t) => ({
      code: t.code,
      plan_code: t.planCode,
      name: t.name,
      purchase_mode: t.purchaseMode,
      ...(t.purchaseMode !== 'self_service' && { billing_mode: t.billingMode }),
      monthly_price: t.monthlyPrice,
      annual_price: t.annualPrice,
      included_conversations: t.includedConversations,
      extra_conversation_price: t.extraConversationPrice,
      default_extra_spend_limit: t.defaultExtraSpendLimit,
    })),
  };
}

export function writePricingCatalog(
  monoRoot = path.resolve(__dirname, '..', '..', '..', '..', '..'),
) {
  const output = buildPricingCatalog();
  const outDir = path.join(monoRoot, 'generated');
  const outFile = path.join(outDir, 'pricing.json');

  if (!fs.existsSync(outDir)) {
    fs.mkdirSync(outDir, { recursive: true });
  }

  fs.writeFileSync(outFile, JSON.stringify(output, null, 2) + '\n', 'utf-8');

  console.log(`✅ pricing.json written to ${outFile}`);
  console.log(
    `   ${output.plans.length} plans, ${output.addons.length} addons, ${output.extras.length} extras`,
  );
  return outFile;
}

if (typeof require !== 'undefined' && require.main === module) {
  writePricingCatalog();
}
