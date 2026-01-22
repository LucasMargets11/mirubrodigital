const currencyFormatter = new Intl.NumberFormat('es-AR', {
  style: 'currency',
  currency: 'ARS',
  maximumFractionDigits: 2,
});

const currencyCompactFormatter = new Intl.NumberFormat('es-AR', {
  style: 'currency',
  currency: 'ARS',
  notation: 'compact',
  maximumFractionDigits: 1,
});

const compactFormatter = new Intl.NumberFormat('es-AR', {
  notation: 'compact',
  maximumFractionDigits: 1,
});

const dateShortFormatter = new Intl.DateTimeFormat('es-AR', {
  day: '2-digit',
  month: '2-digit',
});

const dateLongFormatter = new Intl.DateTimeFormat('es-AR', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
});

const paymentLabels: Record<string, string> = {
  CASH: 'Efectivo',
  CARD: 'Tarjeta',
  CREDIT: 'Crédito',
  DEBIT: 'Débito',
  TRANSFER: 'Transferencia',
  WIRE: 'Transferencia',
  BANK_TRANSFER: 'Transferencia',
  MP: 'Mercado Pago',
  MERCADO_PAGO: 'Mercado Pago',
  MERCADOPAGO: 'Mercado Pago',
  QR: 'Pago QR',
  PIX: 'PIX',
  WALLET: 'Billetera',
  ACCOUNT: 'Cuenta corriente',
  OTHER: 'Otros',
  OTHERS: 'Otros',
};

export function toNumber(value?: string | number | null): number {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : 0;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const normalized = value.replace(',', '.');
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

export function formatARS(value?: string | number | null): string {
  return currencyFormatter.format(toNumber(value));
}

export function formatARSCompact(value?: string | number | null): string {
  return currencyCompactFormatter.format(toNumber(value));
}

export function compactNumber(value?: number | string | null): string {
  if (value === null || value === undefined) {
    return '0';
  }
  return compactFormatter.format(toNumber(value as string | number));
}

export function formatDateShort(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value);
  return dateShortFormatter.format(date);
}

export function formatDateLong(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value);
  return dateLongFormatter.format(date);
}

export function humanizePaymentMethod(method?: string | null): string {
  if (!method) {
    return 'Otros';
  }
  const normalized = method.trim().replace(/\s+/g, '_').replace(/-/g, '_').toUpperCase();
  if (paymentLabels[normalized]) {
    return paymentLabels[normalized];
  }
  return toTitleCase(method.replace(/[_-]+/g, ' '));
}

function toTitleCase(text: string) {
  return text
    .toLowerCase()
    .split(' ')
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ') || 'Otros';
}
