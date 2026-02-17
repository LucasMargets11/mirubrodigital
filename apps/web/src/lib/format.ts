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

/**
 * Formatea un número de manera inteligente:
 * - Si es entero (termina en .00): sin decimales
 * - Si tiene fracción: con 2 decimales
 * Ejemplo: 1.00 → "1", 3.50 → "3,50"
 */
export function formatNumberSmart(value: string | number | null | undefined): string {
  if (value === null || value === undefined) {
    return '0';
  }
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) {
    return '0';
  }

  // Detectar si es entero (sin fracción real)
  const isInteger = Math.abs(numeric - Math.round(numeric)) < 1e-9;

  if (isInteger) {
    return new Intl.NumberFormat('es-AR', {
      maximumFractionDigits: 0,
    }).format(numeric);
  } else {
    return new Intl.NumberFormat('es-AR', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(numeric);
  }
}

/**
 * Formatea moneda de manera inteligente para Argentina:
 * - Si es entero: $ 6.975 (sin ,00)
 * - Si tiene centavos: $ 6.975,50
 * Separador de miles: punto (.)
 * Separador de decimales: coma (,)
 */
export function formatCurrencySmart(value: string | number | null | undefined): string {
  if (value === null || value === undefined) {
    return '$ 0';
  }
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) {
    return '$ 0';
  }

  const formatted = formatNumberSmart(numeric);
  return `$ ${formatted}`;
}
