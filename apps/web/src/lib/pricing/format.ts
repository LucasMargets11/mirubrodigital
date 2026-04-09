/**
 * Pricing-specific currency formatter.
 *
 * Input: ARS pesos integer (e.g. 36000).
 * Output: Formatted string (e.g. "$ 36.000").
 *
 * Does NOT divide by 100 — the canonical unit is already pesos.
 */

const arsFormatter = new Intl.NumberFormat('es-AR', {
  style: 'currency',
  currency: 'ARS',
  maximumFractionDigits: 0,
});

export function formatPrice(arsInteger: number): string {
  return arsFormatter.format(arsInteger);
}
