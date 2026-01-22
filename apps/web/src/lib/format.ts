const currencyFormatter = new Intl.NumberFormat('es-AR', {
  style: 'currency',
  currency: 'ARS',
  maximumFractionDigits: 2,
});

type NumericInput = string | number | null | undefined;

function formatAmount(value: NumericInput): string {
  if (value === null || value === undefined) {
    return currencyFormatter.format(0);
  }
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) {
    return currencyFormatter.format(0);
  }
  return currencyFormatter.format(numeric);
}

export function formatARS(value: NumericInput): string {
  return formatAmount(value);
}

export function formatCurrency(value: NumericInput): string {
  return formatAmount(value);
}

export function formatNumber(value: string | number | null | undefined, options?: Intl.NumberFormatOptions): string {
  if (value === null || value === undefined) {
    return '0';
  }
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) {
    return '0';
  }
  return new Intl.NumberFormat('es-AR', options).format(numeric);
}
