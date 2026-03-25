import type {
  TaxStatus,
  AllocationType,
  DocumentType,
  PaymentMethod,
  DuplicateStatus,
} from '@/lib/api/tax-backup';

// ── Tax Status ───────────────────────────────────────────────────────────────

export const TAX_STATUS_CONFIG: Record<
  TaxStatus,
  {
    label: string;
    shortLabel: string;
    bg: string;
    text: string;
    border: string;
    ringColor: string;
    iconBg: string;
    priority: 'success' | 'warning' | 'danger' | 'info';
  }
> = {
  registrado: {
    label: 'Registrado',
    shortLabel: 'Registrado',
    bg: 'bg-slate-100',
    text: 'text-slate-700',
    border: 'border-slate-200',
    ringColor: 'ring-slate-300',
    iconBg: 'bg-slate-200',
    priority: 'info',
  },
  respaldado: {
    label: 'Con respaldo fiscal',
    shortLabel: 'Respaldado',
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
    ringColor: 'ring-emerald-300',
    iconBg: 'bg-emerald-100',
    priority: 'success',
  },
  potencialmente_deducible: {
    label: 'Deducción parcial',
    shortLabel: 'Parcial',
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    border: 'border-amber-200',
    ringColor: 'ring-amber-300',
    iconBg: 'bg-amber-100',
    priority: 'warning',
  },
  a_revisar: {
    label: 'Requiere atención',
    shortLabel: 'A revisar',
    bg: 'bg-orange-50',
    text: 'text-orange-700',
    border: 'border-orange-200',
    ringColor: 'ring-orange-300',
    iconBg: 'bg-orange-100',
    priority: 'warning',
  },
  no_respaldado_fiscalmente: {
    label: 'Sin respaldo fiscal',
    shortLabel: 'Sin respaldo',
    bg: 'bg-rose-50',
    text: 'text-rose-700',
    border: 'border-rose-200',
    ringColor: 'ring-rose-300',
    iconBg: 'bg-rose-100',
    priority: 'danger',
  },
};

// ── Allocation Type ──────────────────────────────────────────────────────────

export const ALLOCATION_CONFIG: Record<
  AllocationType,
  { label: string; icon: string; description: string }
> = {
  business: {
    label: 'Negocio',
    icon: '🏢',
    description: 'Uso 100% comercial',
  },
  mixed: {
    label: 'Mixto',
    icon: '🔀',
    description: 'Uso compartido personal/comercial',
  },
  personal: {
    label: 'Personal',
    icon: '👤',
    description: 'No vinculado al negocio',
  },
};

// ── Document Type ────────────────────────────────────────────────────────────

export const DOCUMENT_TYPE_OPTIONS: { value: DocumentType; label: string }[] = [
  { value: 'factura', label: 'Factura' },
  { value: 'recibo', label: 'Recibo' },
  { value: 'ticket', label: 'Ticket' },
  { value: 'nota_credito', label: 'Nota de Crédito' },
  { value: 'nota_debito', label: 'Nota de Débito' },
  { value: 'otro', label: 'Otro' },
];

// ── Payment Method ───────────────────────────────────────────────────────────

export const PAYMENT_METHOD_OPTIONS: {
  value: PaymentMethod;
  label: string;
}[] = [
  { value: 'cash', label: 'Efectivo' },
  { value: 'transfer', label: 'Transferencia' },
  { value: 'card', label: 'Tarjeta' },
  { value: 'mercadopago', label: 'MercadoPago' },
  { value: 'check', label: 'Cheque' },
  { value: 'other', label: 'Otro' },
];

export const PAYMENT_METHOD_LABELS: Record<PaymentMethod, string> = {
  cash: 'Efectivo',
  transfer: 'Transferencia',
  card: 'Tarjeta',
  mercadopago: 'MercadoPago',
  check: 'Cheque',
  other: 'Otro',
};


// ── Duplicate Status ─────────────────────────────────────────────────────────

export const DUPLICATE_STATUS_CONFIG: Record<
  DuplicateStatus,
  { label: string; bg: string; text: string }
> = {
  pending: { label: 'Pendiente', bg: 'bg-amber-100', text: 'text-amber-700' },
  confirmed_duplicate: {
    label: 'Duplicado confirmado',
    bg: 'bg-rose-100',
    text: 'text-rose-700',
  },
  dismissed: {
    label: 'Descartado',
    bg: 'bg-slate-100',
    text: 'text-slate-600',
  },
};

// ── Dashboard Stat Cards ─────────────────────────────────────────────────────

export const DASHBOARD_STAT_CARDS = [
  {
    key: 'total' as const,
    label: 'Total',
    cardClass: 'bg-slate-900 text-white',
    textClass: 'text-slate-300',
  },
  {
    key: 'respaldado' as const,
    label: 'Con respaldo',
    cardClass: 'bg-emerald-50 border-emerald-200',
    textClass: 'text-emerald-600',
  },
  {
    key: 'potencialmente_deducible' as const,
    label: 'Pot. deducible',
    cardClass: 'bg-amber-50 border-amber-200',
    textClass: 'text-amber-700',
  },
  {
    key: 'a_revisar' as const,
    label: 'A revisar',
    cardClass: 'bg-amber-50 border-amber-300',
    textClass: 'text-amber-600',
  },
  {
    key: 'no_respaldado_fiscalmente' as const,
    label: 'Sin respaldo',
    cardClass: 'bg-rose-50 border-rose-200',
    textClass: 'text-rose-600',
  },
  {
    key: 'registrado' as const,
    label: 'Registrado',
    cardClass: 'bg-slate-50 border-slate-200',
    textClass: 'text-slate-600',
  },
] as const;

// ── Pagination ───────────────────────────────────────────────────────────────

export const PAGE_SIZE = 50;

// ── File Upload ──────────────────────────────────────────────────────────────

export const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
export const ACCEPTED_FILE_TYPES = '.pdf,.jpg,.jpeg,.png,.webp';
export const ACCEPTED_MIME_TYPES = [
  'application/pdf',
  'image/jpeg',
  'image/png',
  'image/webp',
];

// ── Legal Disclaimer ─────────────────────────────────────────────────────────

export const DISCLAIMER_TEXT =
  'Este módulo organiza tu documentación fiscal con fines de orden interno. No reemplaza el asesoramiento de un contador público.';
