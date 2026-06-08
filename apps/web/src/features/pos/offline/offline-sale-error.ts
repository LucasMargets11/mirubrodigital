/**
 * Human-readable presentation helpers for the offline POS sale queue (PR-OFF-06).
 *
 * The sync engine stores a raw `last_error` string and a status on each queued
 * sale. The UI needs friendlier, operator-facing copy. These helpers translate
 * the stored metadata into readable Spanish messages and payment labels.
 *
 * Pure functions, no React — directly unit-testable.
 */

import type {
  OfflinePaymentMethodCode,
  OfflineSalePaymentSnapshot,
  OfflineSaleQueueItem,
} from './offline-sales-types';

const PAYMENT_METHOD_LABELS: Record<OfflinePaymentMethodCode, string> = {
  cash: 'Efectivo',
  transfer: 'Transferencia',
  card: 'Tarjeta',
  other: 'Otro',
};

/** Label for a single payment method code. */
export function paymentMethodLabel(method: OfflinePaymentMethodCode): string {
  return PAYMENT_METHOD_LABELS[method] ?? 'Otro';
}

/**
 * Joins the distinct payment methods of a sale into a readable label, e.g.
 * "Efectivo" or "Efectivo + Tarjeta". Falls back to "—" when there are none.
 */
export function describeOfflineSalePayments(
  payments: OfflineSalePaymentSnapshot[],
): string {
  if (!payments?.length) return '—';
  const seen = new Set<string>();
  const labels: string[] = [];
  for (const payment of payments) {
    const label = paymentMethodLabel(payment.method);
    if (!seen.has(label)) {
      seen.add(label);
      labels.push(label);
    }
  }
  return labels.join(' + ');
}

/**
 * Produces a readable error message for a `failed`/`conflict` sale, or null for
 * any other status. Normalises the most common backend/engine errors (auth,
 * stock, closed cash drawer, network, conflict) and otherwise falls back to the
 * raw message or a generic "unknown error" copy.
 */
export function describeOfflineSaleError(sale: OfflineSaleQueueItem): string | null {
  if (sale.status !== 'failed' && sale.status !== 'conflict') {
    return null;
  }

  if (sale.status === 'conflict') {
    return 'Conflicto con el servidor. Revisá esta venta antes de reintentar.';
  }

  const raw = (sale.last_error ?? '').toLowerCase();

  if (raw.includes('autoriz') || raw.includes('sesión') || raw.includes('sesion')) {
    return 'Sesión no autorizada. Volvé a iniciar sesión en el POS.';
  }
  if (raw.includes('stock')) {
    return 'Stock insuficiente para uno o más productos.';
  }
  if (raw.includes('caja')) {
    return 'La caja está cerrada. Abrí una caja para registrar la venta.';
  }
  if (
    raw.includes('red') ||
    raw.includes('conexión') ||
    raw.includes('conexion') ||
    raw.includes('network')
  ) {
    return 'Error de red al sincronizar. Se reintentará automáticamente.';
  }

  return sale.last_error || 'Error desconocido al sincronizar.';
}
