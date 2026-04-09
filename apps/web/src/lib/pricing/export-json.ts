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

const output = {
  version: new Date().toISOString().slice(0, 10),
  unit: 'ARS_pesos_integer',
  plans: ALL_PLANS.map((p) => ({
    code: p.code,
    vertical: p.vertical,
    name: p.name,
    price_monthly: p.priceMonthly,
    price_yearly: p.priceYearly,
    is_custom: p.isCustom ?? false,
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
  })),
};

// Resolve monorepo root (5 levels up from this file)
const monoRoot = path.resolve(__dirname, '..', '..', '..', '..', '..');
const outDir = path.join(monoRoot, 'generated');
const outFile = path.join(outDir, 'pricing.json');

if (!fs.existsSync(outDir)) {
  fs.mkdirSync(outDir, { recursive: true });
}

fs.writeFileSync(outFile, JSON.stringify(output, null, 2) + '\n', 'utf-8');

console.log(`✅ pricing.json written to ${outFile}`);
console.log(`   ${output.plans.length} plans, ${output.addons.length} addons, ${output.extras.length} extras`);
