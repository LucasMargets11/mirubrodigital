import { formatNumber } from '@/lib/format';
import type { StockAlertStatus } from '../types';

export type StockStatusTone = 'danger' | 'warning';

export function getStockStatusTone(status: StockAlertStatus): StockStatusTone {
  return status === 'OUT' ? 'danger' : 'warning';
}

export function humanizeStockStatus(status: StockAlertStatus, threshold: string): string {
  if (status === 'OUT') {
    return 'Sin stock';
  }
  const numericThreshold = Number(threshold);
  const formatted = Number.isFinite(numericThreshold) ? formatNumber(numericThreshold) : threshold;
  return `Bajo stock (≤ ${formatted})`;
}

export function getStockStatusIcon(status: StockAlertStatus): string {
  return status === 'OUT' ? '⚠' : '!';
}
