/**
 * View-model layer: maps technical backend states to user-facing operational labels.
 * Keeps the UI decoupled from internal processing vocabulary.
 */

import type {
  FiscalProfileDetail,
  FiscalDocument,
  FiscalStatus,
  TaxStatus,
  CompletionItem,
} from '@/lib/api/tax-backup';

// ── Operational status (what the user sees) ────────────────────────────────

export type OperationalStatus =
  | 'sin_comprobante'
  | 'escaneando'
  | 'lectura_parcial'
  | 'diferencias'
  | 'listo_confirmar'
  | 'validado'
  | 'requiere_reemplazo';

export interface OperationalStatusInfo {
  key: OperationalStatus;
  label: string;
  description: string;
  actionLabel: string | null;
  priority: 'success' | 'warning' | 'danger' | 'info' | 'processing';
  bg: string;
  text: string;
  border: string;
  iconBg: string;
}

export const OPERATIONAL_STATUS_MAP: Record<OperationalStatus, OperationalStatusInfo> = {
  sin_comprobante: {
    key: 'sin_comprobante',
    label: 'Sin comprobante',
    description: 'Este gasto todavía no tiene un comprobante adjunto. Subí una factura, recibo o ticket para respaldar el gasto.',
    actionLabel: 'Subir comprobante',
    priority: 'info',
    bg: 'bg-slate-50',
    text: 'text-slate-700',
    border: 'border-slate-200',
    iconBg: 'bg-slate-100',
  },
  escaneando: {
    key: 'escaneando',
    label: 'Escaneando comprobante',
    description: 'El sistema está analizando tu comprobante. Esto suele tomar unos segundos.',
    actionLabel: null,
    priority: 'processing',
    bg: 'bg-sky-50',
    text: 'text-sky-700',
    border: 'border-sky-200',
    iconBg: 'bg-sky-100',
  },
  lectura_parcial: {
    key: 'lectura_parcial',
    label: 'Lectura parcial',
    description: 'El sistema pudo leer parte del comprobante pero faltan datos. Revisá qué información completar.',
    actionLabel: 'Completar datos',
    priority: 'warning',
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    border: 'border-amber-200',
    iconBg: 'bg-amber-100',
  },
  diferencias: {
    key: 'diferencias',
    label: 'Diferencias con el gasto',
    description: 'Los datos del comprobante no coinciden completamente con el gasto registrado. Revisá las diferencias.',
    actionLabel: 'Ver diferencias',
    priority: 'warning',
    bg: 'bg-orange-50',
    text: 'text-orange-700',
    border: 'border-orange-200',
    iconBg: 'bg-orange-100',
  },
  listo_confirmar: {
    key: 'listo_confirmar',
    label: 'Listo para confirmar',
    description: 'El comprobante fue leído correctamente y los datos coinciden con el gasto. Podés confirmar para completar el respaldo.',
    actionLabel: 'Confirmar datos',
    priority: 'success',
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
    iconBg: 'bg-emerald-100',
  },
  validado: {
    key: 'validado',
    label: 'Validado',
    description: 'Este comprobante está completo y validado. El respaldo fiscal de este gasto está en orden.',
    actionLabel: null,
    priority: 'success',
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
    iconBg: 'bg-emerald-100',
  },
  requiere_reemplazo: {
    key: 'requiere_reemplazo',
    label: 'Requiere reemplazo',
    description: 'El comprobante actual no es válido o no se pudo procesar. Reemplazalo por uno legible y correcto.',
    actionLabel: 'Reemplazar comprobante',
    priority: 'danger',
    bg: 'bg-rose-50',
    text: 'text-rose-700',
    border: 'border-rose-200',
    iconBg: 'bg-rose-100',
  },
};

// ── Derive operational status from backend data ────────────────────────────

export function deriveOperationalStatus(
  profile: FiscalProfileDetail,
): OperationalStatus {
  const docs = profile.documents ?? [];
  const hasDocs = docs.length > 0;

  if (!hasDocs) return 'sin_comprobante';

  // Check if any doc is being processed
  const anyPending = docs.some((d) => d.parse_status === 'pending');
  if (anyPending) return 'escaneando';

  // Check if any doc failed extraction entirely
  const allFailed = docs.every((d) => d.parse_status === 'failed');
  if (allFailed) return 'requiere_reemplazo';

  // Check fiscal/tax status
  const { fiscal_status, tax_status, validation_issues, missing_fields } = profile;

  // Fully valid
  if (
    fiscal_status === 'valido' &&
    (tax_status === 'respaldado' || tax_status === 'potencialmente_deducible')
  ) {
    return 'validado';
  }

  // Has validation issues (mismatches)
  if (
    validation_issues &&
    validation_issues.length > 0 &&
    fiscal_status !== 'sin_comprobante'
  ) {
    return 'diferencias';
  }

  // Incomplete extraction
  if (
    fiscal_status === 'incompleto' ||
    (missing_fields && missing_fields.length > 0)
  ) {
    return 'lectura_parcial';
  }

  // Requires review but no specific issues → ready to confirm
  if (
    fiscal_status === 'valido_con_observaciones' ||
    fiscal_status === 'requiere_revision'
  ) {
    return hasDocs ? 'diferencias' : 'sin_comprobante';
  }

  // Has documents, parsed successfully, and no issues
  const anyParsed = docs.some((d) => d.parse_status === 'parsed');
  if (anyParsed && (!validation_issues || validation_issues.length === 0)) {
    return 'listo_confirmar';
  }

  return 'lectura_parcial';
}

// ── Comparison items gasto vs comprobante ──────────────────────────────────

export interface ComparisonField {
  key: string;
  label: string;
  expected: string | null;
  detected: string | null;
  matches: boolean | null; // null = can't compare (missing data)
}

export function buildComparison(
  profile: FiscalProfileDetail,
  doc: FiscalDocument | null,
): ComparisonField[] {
  const fields: ComparisonField[] = [];

  const expectedAmount = profile.source_amount
    ? parseFloat(profile.source_amount)
    : null;
  const detectedAmount = doc?.total ? parseFloat(doc.total) : null;

  fields.push({
    key: 'monto',
    label: 'Monto',
    expected: expectedAmount != null ? `$${expectedAmount.toLocaleString('es-AR', { minimumFractionDigits: 2 })}` : null,
    detected: detectedAmount != null ? `$${detectedAmount.toLocaleString('es-AR', { minimumFractionDigits: 2 })}` : null,
    matches:
      expectedAmount != null && detectedAmount != null
        ? Math.abs(expectedAmount - detectedAmount) < 0.01
        : null,
  });

  fields.push({
    key: 'fecha',
    label: 'Fecha / Período',
    expected: profile.source_period_label ?? profile.source_due_date ?? null,
    detected: doc?.issue_date ?? null,
    matches:
      profile.source_due_date && doc?.issue_date
        ? profile.source_due_date === doc.issue_date
        : null,
  });

  fields.push({
    key: 'moneda',
    label: 'Moneda',
    expected: 'ARS', // most common default
    detected: doc?.currency || null,
    matches:
      doc?.currency
        ? doc.currency === 'ARS'
        : null,
  });

  // Use subtype (e.g. "Factura A") if available, otherwise generic category
  const detectedTypeLabel = doc?.document_subtype
    ?? (doc?.document_type
      ? { factura: 'Factura', recibo: 'Recibo', ticket: 'Ticket', nota_credito: 'Nota de Crédito', nota_debito: 'Nota de Débito', otro: 'Otro' }[doc.document_type] ?? doc.document_type
      : null);

  fields.push({
    key: 'tipo_comprobante',
    label: 'Tipo de comprobante',
    expected: 'Factura', // business expectation
    detected: detectedTypeLabel,
    matches: doc?.document_type ? doc.document_type === 'factura' : null,
  });

  fields.push({
    key: 'cuit_comprador',
    label: 'CUIT Comprador',
    expected: 'Registrado', // should match business CUIT
    detected: doc?.buyer_tax_id ?? null,
    matches: doc?.buyer_tax_id ? true : null, // present = ok for now
  });

  return fields;
}

// ── Recommended actions ────────────────────────────────────────────────────

export interface RecommendedAction {
  key: string;
  label: string;
  description: string;
  variant: 'primary' | 'secondary' | 'outline';
  actionType: 'upload' | 'confirm' | 'edit' | 'replace' | 'defer' | 'payment' | 'technical';
}

export function getRecommendedActions(
  profile: FiscalProfileDetail,
  opStatus: OperationalStatus,
): RecommendedAction[] {
  const actions: RecommendedAction[] = [];

  switch (opStatus) {
    case 'sin_comprobante':
      actions.push({
        key: 'upload',
        label: 'Subir comprobante',
        description: 'Adjuntá una factura, recibo o ticket',
        variant: 'primary',
        actionType: 'upload',
      });
      break;
    case 'escaneando':
      // No actions while processing
      break;
    case 'lectura_parcial':
      actions.push({
        key: 'edit',
        label: 'Completar datos manualmente',
        description: 'Agregá la información que falta',
        variant: 'primary',
        actionType: 'edit',
      });
      actions.push({
        key: 'replace',
        label: 'Reemplazar comprobante',
        description: 'Subí una versión más legible',
        variant: 'outline',
        actionType: 'replace',
      });
      break;
    case 'diferencias':
      actions.push({
        key: 'edit',
        label: 'Corregir datos',
        description: 'Ajustá los datos que no coinciden',
        variant: 'primary',
        actionType: 'edit',
      });
      actions.push({
        key: 'confirm',
        label: 'Confirmar de todas formas',
        description: 'Si los datos son correctos, confirmá',
        variant: 'secondary',
        actionType: 'confirm',
      });
      break;
    case 'listo_confirmar':
      actions.push({
        key: 'confirm',
        label: 'Confirmar datos',
        description: 'Todo parece correcto. Confirmá para validar.',
        variant: 'primary',
        actionType: 'confirm',
      });
      break;
    case 'requiere_reemplazo':
      actions.push({
        key: 'replace',
        label: 'Reemplazar comprobante',
        description: 'Subí un comprobante válido y legible',
        variant: 'primary',
        actionType: 'replace',
      });
      break;
    case 'validado':
      // Already done
      break;
  }

  // Common secondary actions
  if (opStatus !== 'sin_comprobante' && opStatus !== 'escaneando') {
    actions.push({
      key: 'defer',
      label: 'Revisar después',
      description: 'Marcá este gasto para revisión posterior',
      variant: 'outline',
      actionType: 'defer',
    });
  }

  // Payment if none recorded
  const hasPayments = (profile.payment_details ?? []).length > 0;
  if (!hasPayments && opStatus !== 'sin_comprobante') {
    actions.push({
      key: 'payment',
      label: 'Registrar pago',
      description: 'Agregá el comprobante de pago',
      variant: 'outline',
      actionType: 'payment',
    });
  }

  return actions;
}

// ── File type helpers ──────────────────────────────────────────────────────

export function getFileType(url: string | null): 'pdf' | 'image' | 'unknown' {
  if (!url) return 'unknown';
  const lower = url.toLowerCase();
  if (lower.includes('.pdf') || lower.includes('application/pdf')) return 'pdf';
  if (
    lower.includes('.jpg') ||
    lower.includes('.jpeg') ||
    lower.includes('.png') ||
    lower.includes('.webp') ||
    lower.includes('image/')
  ) return 'image';
  return 'unknown';
}

// ── Parse status label ─────────────────────────────────────────────────────

export function parseStatusLabel(status: FiscalDocument['parse_status']): string {
  switch (status) {
    case 'manual': return 'Carga manual';
    case 'pending': return 'Procesando';
    case 'parsed': return 'Datos extraídos';
    case 'failed': return 'Extracción fallida';
    default: return status;
  }
}
