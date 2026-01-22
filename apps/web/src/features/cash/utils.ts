import type { CashMovementCategory, CashMovementType, CashPaymentMethod, SalesWithBalance } from './types';

const currencyFormatter = new Intl.NumberFormat('es-AR', {
  style: 'currency',
  currency: 'ARS',
  maximumFractionDigits: 2,
});

export function formatCurrency(value: string | number | null | undefined): string {
  if (value === null || value === undefined) {
    return currencyFormatter.format(0);
  }
  const numeric = typeof value === 'number' ? value : Number(value);
  return currencyFormatter.format(Number.isNaN(numeric) ? 0 : numeric);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return '—';
  }
  return new Date(value).toLocaleString('es-AR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

export function toNumber(value: string | number | null | undefined): number {
  if (value === null || value === undefined) {
    return 0;
  }
  return typeof value === 'number' ? value : Number(value);
}

const methodLabels: Record<CashPaymentMethod, string> = {
  cash: 'Efectivo',
  debit: 'Débito',
  credit: 'Crédito',
  transfer: 'Transferencia',
  wallet: 'Billetera',
  account: 'Cuenta corriente',
};

export function getMethodLabel(method: CashPaymentMethod): string {
  return methodLabels[method] ?? method;
}

export const movementTypeLabels: Record<CashMovementType, string> = {
  in: 'Ingreso',
  out: 'Egreso',
};

export const movementCategoryLabels: Record<CashMovementCategory, string> = {
  expense: 'Gasto',
  withdraw: 'Retiro',
  deposit: 'Depósito',
  other: 'Otro',
};

export const paymentMethodOptions = (
  Object.entries(methodLabels) as Array<[CashPaymentMethod, string]>
).map(([value, label]) => ({ value, label }));

export const movementTypeOptions: { value: CashMovementType; label: string }[] = [
  { value: 'in', label: 'Ingreso' },
  { value: 'out', label: 'Egreso' },
];

export const movementCategoryOptions: { value: CashMovementCategory; label: string }[] = (
  Object.entries(movementCategoryLabels) as Array<[CashMovementCategory, string]>
).map(([value, label]) => ({ value, label }));

export function getSaleBalanceValue(sale: SalesWithBalance): number {
  const balanceValue = sale.balance ?? '0';
  return Number(balanceValue);
}

export function isSaleFullyPaid(sale: SalesWithBalance): boolean {
  return getSaleBalanceValue(sale) <= 0.009;
}
