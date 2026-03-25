"use client";

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Loader2,
  RefreshCcw,
  FileText,
  CreditCard,
  Trash2,
  Plus,
  X,
  CheckCircle2,
  Circle,
  AlertCircle,
  ArrowRight,
  ShieldCheck,
  ShieldAlert,
  ShieldX,
  Clock,
  ChevronDown,
  ChevronUp,
  Banknote,
  Paperclip,
  Calendar,
  Hash,
  Building2,
  ExternalLink,
  Info,
  Sparkles,
} from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';

import {
  getProfile,
  deleteDocument,
  reEvaluateProfile,
  taxBackupKeys,
  safeAmount,
  type FiscalProfileDetail,
  type FiscalDocument,
  type CompletionItem,
  type PaymentDetail,
  type StatusLog,
  type TaxStatus,
  type FiscalStatus,
} from '@/lib/api/tax-backup';
import { Currency } from '../../components/currency';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  TAX_STATUS_CONFIG,
  FISCAL_STATUS_CONFIG,
  ALLOCATION_CONFIG,
  DOCUMENT_TYPE_OPTIONS,
  PAYMENT_METHOD_LABELS,
  DISCLAIMER_TEXT,
} from './constants';
import { DocumentUpload } from './document-upload';
import { PaymentForm } from './payment-form';

// ── Status icon mapping ─────────────────────────────────────────────────────

function StatusIcon({ status, className }: { status: TaxStatus; className?: string }) {
  const cfg = TAX_STATUS_CONFIG[status];
  const iconClass = cn('h-5 w-5', className);
  switch (cfg.priority) {
    case 'success':
      return <ShieldCheck className={cn(iconClass, 'text-emerald-600')} />;
    case 'warning':
      return <ShieldAlert className={cn(iconClass, 'text-orange-500')} />;
    case 'danger':
      return <ShieldX className={cn(iconClass, 'text-rose-600')} />;
    default:
      return <Clock className={cn(iconClass, 'text-slate-500')} />;
  }
}

// ── Main component ──────────────────────────────────────────────────────────

interface Props {
  profileId: number;
  onClose: () => void;
  canManage: boolean;
}

export function TaxBackupDetail({ profileId, onClose, canManage }: Props) {
  const queryClient = useQueryClient();
  const [showUpload, setShowUpload] = useState(false);
  const [showPayment, setShowPayment] = useState(false);
  const [showTimeline, setShowTimeline] = useState(false);

  const {
    data: profile,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: taxBackupKeys.profile(profileId),
    queryFn: () => getProfile(profileId),
  });

  const reEvalMutation = useMutation({
    mutationFn: () => reEvaluateProfile(profileId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: taxBackupKeys.profile(profileId),
      });
      queryClient.invalidateQueries({ queryKey: taxBackupKeys.summary() });
    },
  });

  const deleteDocMutation = useMutation({
    mutationFn: (docId: number) => deleteDocument(profileId, docId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: taxBackupKeys.profile(profileId),
      });
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-16">
        <Loader2 className="h-7 w-7 animate-spin text-slate-400" />
      </div>
    );
  }

  if (isError || !profile) {
    return (
      <div className="flex flex-col items-center justify-center p-16 text-center gap-3">
        <AlertCircle className="h-8 w-8 text-slate-300" />
        <p className="text-sm text-slate-500">No se pudo cargar el perfil fiscal</p>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          Reintentar
        </Button>
      </div>
    );
  }

  const p = profile as FiscalProfileDetail;
  const statusCfg = TAX_STATUS_CONFIG[p.tax_status];
  const allocCfg = ALLOCATION_CONFIG[p.allocation_type];
  const completionScore = (p.completion_items ?? []).filter(
    (c) => c.applicable && c.done,
  ).length;
  const completionTotal = (p.completion_items ?? []).filter(
    (c) => c.applicable,
  ).length;
  const isBacked = p.tax_status === 'respaldado';

  return (
    <div className="space-y-5">
      {/* 1. HEADER — Profile identity */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-xl font-bold text-slate-900 leading-tight truncate">
              {p.source_name || 'Gasto sin nombre'}
            </h3>
            {p.source_type === 'fixed_expense_period' ? (
              <span className="inline-flex items-center gap-1 text-xs font-semibold text-violet-700 bg-violet-100 px-2 py-0.5 rounded-md border border-violet-200">
                Fijo
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-xs font-semibold text-sky-700 bg-sky-50 px-2 py-0.5 rounded-md border border-sky-200">
                Puntual
              </span>
            )}
          </div>

          {/* Meta row: amount + period + allocation */}
          <div className="flex items-center gap-3 mt-1.5 flex-wrap text-sm">
            <span className="font-semibold text-slate-800 tabular-nums">
              {p.source_amount != null ? (
                <Currency amount={safeAmount(p.source_amount)} />
              ) : (
                <span className="text-slate-400">Monto no disponible</span>
              )}
            </span>
            {p.source_period_label && (
              <span className="flex items-center gap-1 text-slate-500">
                <Calendar className="h-3.5 w-3.5" />
                {p.source_period_label}
              </span>
            )}
            <span className="flex items-center gap-1 text-slate-500">
              {allocCfg.icon} {allocCfg.label}
            </span>
          </div>
        </div>

        <button
          onClick={onClose}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors shrink-0"
          aria-label="Cerrar detalle"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* 2. STATUS CARD — Primary status + guidance */}
      <div
        className={cn(
          'rounded-xl border-2 p-4',
          statusCfg.border,
          statusCfg.bg,
        )}
        role="status"
        aria-label={`Estado fiscal: ${p.human_status_title || statusCfg.label}`}
      >
        <div className="flex items-start gap-3">
          <div className={cn('p-2 rounded-lg shrink-0', statusCfg.iconBg)}>
            <StatusIcon status={p.tax_status} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h4 className={cn('font-bold text-base', statusCfg.text)}>
                {p.human_status_title || statusCfg.label}
              </h4>
              <span
                className={cn(
                  'inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold tracking-wide uppercase',
                  statusCfg.bg,
                  statusCfg.text,
                  'border',
                  statusCfg.border,
                )}
              >
                {statusCfg.shortLabel}
              </span>
            </div>
            <p className={cn('text-sm mt-1 leading-relaxed', statusCfg.text, 'opacity-80')}>
              {p.human_status_description || 'Estado fiscal de este gasto.'}
            </p>
            {p.next_recommended_action && !isBacked && (
              <div className="flex items-start gap-2 mt-3 p-2.5 bg-white/70 rounded-lg border border-white/50">
                <ArrowRight className={cn('h-4 w-4 mt-0.5 shrink-0', statusCfg.text)} />
                <p className="text-sm font-medium text-slate-800">
                  {p.next_recommended_action}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Review reason — technical detail, collapsible */}
        {p.review_reason && (
          <details className="mt-3 group">
            <summary className="text-xs font-medium text-slate-500 cursor-pointer hover:text-slate-700 flex items-center gap-1">
              <Info className="h-3 w-3" />
              Detalle técnico
            </summary>
            <p className="mt-1.5 text-xs text-slate-500 bg-white/60 rounded-md p-2 leading-relaxed">
              {p.review_reason}
            </p>
          </details>
        )}
      </div>

      {/* 2b. FISCAL STATUS CARD — Sprint 4 documentary validation */}
      <FiscalStatusCard profile={p} />

      {/* 3. COMPLETION CHECKLIST — "Qué falta" */}
      {completionTotal > 0 && (
        <section aria-labelledby="completion-heading">
          <div className="flex items-center justify-between mb-3">
            <h4 id="completion-heading" className="text-sm font-bold text-slate-800">
              Qué falta completar
            </h4>
            <span
              className={cn(
                'text-xs font-semibold px-2 py-0.5 rounded-full',
                completionScore === completionTotal
                  ? 'bg-emerald-100 text-emerald-700'
                  : 'bg-slate-100 text-slate-600',
              )}
            >
              {completionScore}/{completionTotal}
            </span>
          </div>
          {/* Progress bar */}
          <div
            className="w-full bg-slate-100 rounded-full h-1.5 mb-3"
            role="progressbar"
            aria-valuenow={completionScore}
            aria-valuemax={completionTotal}
          >
            <div
              className={cn(
                'h-1.5 rounded-full transition-all duration-500',
                completionScore === completionTotal ? 'bg-emerald-500' : 'bg-indigo-500',
              )}
              style={{ width: `${completionTotal > 0 ? (completionScore / completionTotal) * 100 : 0}%` }}
            />
          </div>
          <ul className="space-y-1.5">
            {(p.completion_items ?? []).map((item: CompletionItem) => {
              if (!item.applicable) return null;
              return (
                <li
                  key={item.key}
                  className={cn(
                    'flex items-start gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors',
                    item.done ? 'bg-emerald-50/60' : 'bg-slate-50',
                  )}
                >
                  {item.done ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 mt-0.5 shrink-0" />
                  ) : (
                    <Circle className="h-4 w-4 text-slate-300 mt-0.5 shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <span
                      className={cn(
                        'font-medium',
                        item.done ? 'text-emerald-700' : 'text-slate-700',
                      )}
                    >
                      {item.label}
                    </span>
                    {!item.done && item.hint && (
                      <p className="text-xs text-slate-500 mt-0.5">{item.hint}</p>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {/* 4. DOCUMENTS SECTION */}
      <section aria-labelledby="docs-heading">
        <div className="flex items-center justify-between mb-3">
          <h4 id="docs-heading" className="text-sm font-bold text-slate-800 flex items-center gap-2">
            <FileText className="h-4 w-4 text-slate-500" />
            Comprobantes
            <span className="text-xs font-normal text-slate-400">
              ({p.documents?.length ?? 0})
            </span>
          </h4>
          {!showUpload && canManage && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowUpload(true)}
              className="gap-1.5"
            >
              <Paperclip className="h-3.5 w-3.5" />
              Adjuntar comprobante
            </Button>
          )}
        </div>

        {showUpload && canManage && (
          <DocumentUpload
            profileId={profileId}
            onUploaded={() => setShowUpload(false)}
            onCancel={() => setShowUpload(false)}
          />
        )}

        {p.documents && p.documents.length > 0 ? (
          <div className="space-y-2">
            {p.documents.map((doc: FiscalDocument) => (
              <DocumentCard
                key={doc.id}
                doc={doc}
                canManage={canManage}
                onDelete={() => deleteDocMutation.mutate(doc.id)}
                isDeleting={deleteDocMutation.isPending}
              />
            ))}
          </div>
        ) : (
          !showUpload && (
            <div className="flex flex-col items-center justify-center py-8 px-4 border-2 border-dashed border-slate-200 rounded-xl text-center">
              <FileText className="h-8 w-8 text-slate-300 mb-2" />
              <p className="text-sm font-medium text-slate-500">
                Sin comprobantes adjuntos
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Adjuntá un comprobante fiscal para respaldar este gasto
              </p>
              {canManage && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowUpload(true)}
                  className="mt-3 gap-1.5"
                >
                  <Paperclip className="h-3.5 w-3.5" />
                  Adjuntar comprobante
                </Button>
              )}
            </div>
          )
        )}
      </section>

      {/* 5. PAYMENTS SECTION */}
      <section aria-labelledby="payments-heading">
        <div className="flex items-center justify-between mb-3">
          <h4 id="payments-heading" className="text-sm font-bold text-slate-800 flex items-center gap-2">
            <Banknote className="h-4 w-4 text-slate-500" />
            Pagos
            <span className="text-xs font-normal text-slate-400">
              ({p.payment_details?.length ?? 0})
            </span>
          </h4>
          {!showPayment && canManage && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowPayment(true)}
              className="gap-1.5"
            >
              <Plus className="h-3.5 w-3.5" />
              Registrar pago
            </Button>
          )}
        </div>

        {showPayment && canManage && (
          <PaymentForm
            profileId={profileId}
            onAdded={() => setShowPayment(false)}
            onCancel={() => setShowPayment(false)}
          />
        )}

        {p.payment_details && p.payment_details.length > 0 ? (
          <div className="space-y-2">
            {p.payment_details.map((pay: PaymentDetail) => (
              <PaymentCard key={pay.id} payment={pay} />
            ))}
          </div>
        ) : (
          !showPayment && (
            <div className="flex flex-col items-center justify-center py-8 px-4 border-2 border-dashed border-slate-200 rounded-xl text-center">
              <Banknote className="h-8 w-8 text-slate-300 mb-2" />
              <p className="text-sm font-medium text-slate-500">
                Sin pagos registrados
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Registrá el pago asociado a este gasto
              </p>
              {canManage && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowPayment(true)}
                  className="mt-3 gap-1.5"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Registrar pago
                </Button>
              )}
            </div>
          )
        )}
      </section>

      {/* 6. TIMELINE — Collapsible, secondary */}
      <section aria-labelledby="timeline-heading">
        <button
          id="timeline-heading"
          onClick={() => setShowTimeline(!showTimeline)}
          className="flex items-center justify-between w-full py-2 text-sm font-bold text-slate-600 hover:text-slate-800 transition-colors group"
          aria-expanded={showTimeline}
        >
          <span className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-slate-400" />
            Historial de cambios
            <span className="text-xs font-normal text-slate-400">
              ({p.status_logs?.length ?? 0})
            </span>
          </span>
          {showTimeline ? (
            <ChevronUp className="h-4 w-4 text-slate-400 group-hover:text-slate-600" />
          ) : (
            <ChevronDown className="h-4 w-4 text-slate-400 group-hover:text-slate-600" />
          )}
        </button>
        {showTimeline && (
          <div className="mt-2">
            <StatusTimelineInline logs={p.status_logs ?? []} />
          </div>
        )}
      </section>

      {/* ACTION BAR */}
      <div className="flex items-center justify-between pt-4 border-t border-slate-100">
        {canManage && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => reEvalMutation.mutate()}
            disabled={reEvalMutation.isPending}
            className="gap-1.5"
          >
            {reEvalMutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCcw className="h-3.5 w-3.5" />
            )}
            Re-evaluar estado
          </Button>
        )}
        {!canManage && <div />}
        <p className="text-[11px] text-slate-400 leading-snug max-w-xs text-right">
          {DISCLAIMER_TEXT}
        </p>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Sub-components
// ═══════════════════════════════════════════════════════════════════════════

/** Structured document card */
function DocumentCard({
  doc,
  canManage,
  onDelete,
  isDeleting,
}: {
  doc: FiscalDocument;
  canManage: boolean;
  onDelete: () => void;
  isDeleting: boolean;
}) {
  const typeLabel =
    DOCUMENT_TYPE_OPTIONS.find((o) => o.value === doc.document_type)?.label ??
    doc.document_type;

  return (
    <div className="rounded-xl border border-slate-200 bg-white hover:border-slate-300 transition-colors overflow-hidden">
      <div className="p-3.5">
        {/* Top row: type + fiscal badge + actions */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-slate-800">
              {typeLabel}
            </span>
            {doc.invoice_number && (
              <span className="flex items-center gap-1 text-xs text-slate-500">
                <Hash className="h-3 w-3" />
                {doc.invoice_number}
              </span>
            )}
            {doc.is_fiscal_document ? (
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-md border border-emerald-200">
                <CheckCircle2 className="h-3 w-3" />
                Fiscal
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-[11px] font-medium bg-slate-50 text-slate-500 px-2 py-0.5 rounded-md border border-slate-200">
                No fiscal
              </span>
            )}
            {doc.parse_status === 'parsed' && (
              <span className="inline-flex items-center gap-1 text-[11px] font-medium bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded-md border border-indigo-200">
                <Sparkles className="h-3 w-3" />
                Datos extraídos
              </span>
            )}
            {doc.parse_status === 'failed' && (
              <span className="inline-flex items-center gap-1 text-[11px] font-medium bg-amber-50 text-amber-600 px-2 py-0.5 rounded-md border border-amber-200">
                <AlertCircle className="h-3 w-3" />
                Extracción fallida
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {doc.file && (
              <a
                href={doc.file}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700 px-2 py-1 rounded-md hover:bg-indigo-50 transition-colors"
                aria-label={`Ver ${typeLabel}`}
              >
                <ExternalLink className="h-3 w-3" />
                Ver
              </a>
            )}
            {canManage && (
              <button
                onClick={onDelete}
                disabled={isDeleting}
                className="p-1.5 rounded-md text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors disabled:opacity-40"
                aria-label="Eliminar comprobante"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Detail row */}
        <div className="flex items-center gap-3 mt-2 text-xs text-slate-500 flex-wrap">
          {doc.issuer_name && (
            <span className="flex items-center gap-1">
              <Building2 className="h-3 w-3" />
              {doc.issuer_name}
            </span>
          )}
          {doc.total && (
            <span className="font-mono font-medium text-slate-700">
              <Currency amount={parseFloat(doc.total)} />
            </span>
          )}
          {doc.issue_date && (
            <span className="flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              {format(parseISO(doc.issue_date), "d 'de' MMM yyyy", { locale: es })}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

/** Structured payment card */
function PaymentCard({ payment }: { payment: PaymentDetail }) {
  const methodLabel =
    PAYMENT_METHOD_LABELS[payment.payment_method] ??
    payment.payment_method;

  return (
    <div className="rounded-xl border border-slate-200 bg-white hover:border-slate-300 transition-colors p-3.5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="p-2 bg-slate-50 rounded-lg shrink-0">
            <CreditCard className="h-4 w-4 text-slate-500" />
          </div>
          <div className="min-w-0">
            <span className="text-sm font-semibold text-slate-800 block">
              {methodLabel}
            </span>
            <div className="flex items-center gap-2 mt-0.5 text-xs text-slate-500 flex-wrap">
              {payment.reference && (
                <span className="truncate">Ref: {payment.reference}</span>
              )}
              {payment.proof_file && (
                <a
                  href={payment.proof_file}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-indigo-600 hover:text-indigo-700 font-medium flex items-center gap-1"
                >
                  <Paperclip className="h-3 w-3" />
                  Comprobante
                </a>
              )}
            </div>
          </div>
        </div>
        <div className="text-right shrink-0">
          <span className="text-sm font-semibold text-slate-800 font-mono tabular-nums block">
            {payment.amount ? (
              <Currency amount={parseFloat(payment.amount)} />
            ) : (
              <span className="text-slate-400">—</span>
            )}
          </span>
          <span className="text-xs text-slate-400 block mt-0.5">
            {format(
              new Date(payment.payment_date || payment.created_at),
              "d MMM yyyy",
              { locale: es },
            )}
          </span>
        </div>
      </div>
    </div>
  );
}

/** Inline timeline (used inside collapsible) */
function StatusTimelineInline({ logs }: { logs: StatusLog[] }) {
  if (!logs.length) {
    return (
      <div className="flex flex-col items-center py-6 text-center">
        <Clock className="h-6 w-6 text-slate-300 mb-1" />
        <p className="text-sm text-slate-400">Sin cambios de estado registrados</p>
      </div>
    );
  }

  const sorted = [...logs].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  const RULE_LABELS: Record<string, string> = {
    RULE_PERSONAL: 'Asignación personal',
    RULE_NO_DOC: 'Sin comprobantes',
    RULE_NO_FISCAL_DOC: 'Sin comprobante fiscal',
    RULE_CAPITAL_ASSET: 'Bien de uso detectado',
    RULE_MIXED: 'Gasto mixto con comprobante',
    RULE_AMOUNT_MISMATCH: 'Diferencia de montos',
    RULE_NO_BUYER_TAX_ID: 'CUIT/RUT faltante',
    RULE_BACKED: 'Respaldo completo',
    RULE_FALLBACK: 'Evaluación inicial',
  };

  return (
    <div className="space-y-0">
      {sorted.map((log, i) => {
        const newCfg = TAX_STATUS_CONFIG[log.new_status];
        const ruleLabel = RULE_LABELS[log.rule_code] || log.rule_code;
        return (
          <div key={log.id} className="flex gap-3">
            <div className="flex flex-col items-center">
              <div
                className={cn(
                  'w-2 h-2 rounded-full mt-2 shrink-0',
                  i === 0 ? 'bg-slate-800' : 'bg-slate-300',
                )}
              />
              {i < sorted.length - 1 && (
                <div className="w-px flex-1 bg-slate-200 mt-1" />
              )}
            </div>
            <div className="pb-3.5 min-w-0">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span
                  className={cn(
                    'inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold',
                    newCfg.bg,
                    newCfg.text,
                    'border',
                    newCfg.border,
                  )}
                >
                  {newCfg.shortLabel}
                </span>
                <span className="text-xs text-slate-500">{ruleLabel}</span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                {format(new Date(log.created_at), "d MMM yyyy, HH:mm", {
                  locale: es,
                })}
              </p>
              {log.note && (
                <p className="text-xs text-slate-400 mt-0.5 italic leading-relaxed">
                  {log.note}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Sprint 4 — Fiscal validation status card */
function FiscalStatusCard({ profile: p }: { profile: FiscalProfileDetail }) {
  const cfg = FISCAL_STATUS_CONFIG[p.fiscal_status];
  if (!cfg) return null;

  const hasIssues = p.validation_issues && p.validation_issues.length > 0;
  const hasMissing = p.missing_fields_labels && p.missing_fields_labels.length > 0;
  const isValid = p.fiscal_status === 'valido';

  return (
    <div
      className={cn(
        'rounded-xl border p-4',
        cfg.border,
        cfg.bg,
      )}
    >
      <div className="flex items-center justify-between mb-1">
        <h4 className={cn('text-sm font-bold', cfg.text)}>
          Validación documental
        </h4>
        <span
          className={cn(
            'inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold tracking-wide uppercase border',
            cfg.bg, cfg.text, cfg.border,
          )}
        >
          {cfg.shortLabel}
        </span>
      </div>

      <p className={cn('text-sm', cfg.text, 'opacity-80')}>
        {p.fiscal_status_label || cfg.label}
      </p>

      {p.review_required && !isValid && (
        <div className="flex items-center gap-1.5 mt-2 text-xs font-medium text-amber-700 bg-amber-50 rounded-md px-2 py-1 border border-amber-200 w-fit">
          <AlertCircle className="h-3 w-3" />
          Revisión requerida
        </div>
      )}

      {hasMissing && (
        <div className="mt-3">
          <p className="text-xs font-semibold text-slate-600 mb-1">Campos faltantes:</p>
          <ul className="space-y-0.5">
            {p.missing_fields_labels.map((f) => (
              <li key={f.key} className="flex items-center gap-1.5 text-xs text-slate-600">
                <Circle className="h-2.5 w-2.5 text-slate-300 shrink-0" />
                {f.label}
              </li>
            ))}
          </ul>
        </div>
      )}

      {hasIssues && (
        <div className="mt-3">
          <p className="text-xs font-semibold text-slate-600 mb-1">Observaciones:</p>
          <ul className="space-y-0.5">
            {p.validation_issues.map((issue, i) => (
              <li key={i} className="flex items-start gap-1.5 text-xs text-slate-600">
                <AlertCircle className="h-3 w-3 text-amber-400 mt-0.5 shrink-0" />
                {issue}
              </li>
            ))}
          </ul>
        </div>
      )}

      {p.evaluated_at && (
        <p className="text-[10px] text-slate-400 mt-3">
          Evaluado: {format(parseISO(p.evaluated_at), "d MMM yyyy, HH:mm", { locale: es })}
          {p.evaluation_source && ` · Fuente: ${p.evaluation_source}`}
        </p>
      )}
    </div>
  );
}
