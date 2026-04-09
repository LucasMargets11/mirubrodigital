/**
 * Canonical extra-resource definitions — single source of truth.
 *
 * Prices: ARS pesos integers.
 *
 * Sources verified against:
 *   - gestion-comercial-catalog.ts  EXTRAS
 *   - docs/PRICING_AUDIT_FULL.md   §2
 */
import type { ExtraDef } from './types';

/**
 * Backend uses 'extra_seat' while frontend catalog uses 'extra_user'.
 * Canonical code is 'extra_user'. Use this constant when mapping to backend.
 */
export const EXTRA_USER_BACKEND_CODE = 'extra_seat';

export const EXTRA_BRANCH: ExtraDef = {
  code: 'extra_branch',
  vertical: 'commercial',
  name: 'Sucursal adicional',
  priceMonthly: 12000,
  priceYearly: 115200,
  availableFor: ['gestion_pro', 'gestion_business'],
};

export const EXTRA_USER: ExtraDef = {
  code: 'extra_user',
  vertical: 'commercial',
  name: 'Usuario adicional',
  priceMonthly: 5000,
  priceYearly: 48000,
  availableFor: ['gestion_pro', 'gestion_business'],
};

export const ALL_EXTRAS: readonly ExtraDef[] = [EXTRA_BRANCH, EXTRA_USER];
