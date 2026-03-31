'use client';

import {
  FileText,
  Hash,
  Calendar,
  Building2,
  DollarSign,
  CreditCard,
  Sparkles,
  User,
  QrCode,
  ScanLine,
  Pencil,
} from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';

import { cn } from '@/lib/utils';
import type { FiscalDocument } from '@/lib/api/tax-backup';
import { parseStatusLabel } from './view-models';

interface ExtractionSummaryProps {
  document: FiscalDocument | null;
  className?: string;
}

interface FieldRowProps {
  icon: React.ReactNode;
  label: string;
  value: string | null | undefined;
  badge?: React.ReactNode;
}

function FieldRow({ icon, label, value, badge }: FieldRowProps) {
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-slate-100 last:border-0">
      <div className="p-1.5 rounded-md bg-slate-50 text-slate-400 shrink-0 mt-0.5" aria-hidden="true">
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-slate-500">{label}</p>
        <p className={cn(
          'text-sm font-medium mt-0.5',
          value ? 'text-slate-800' : 'text-slate-400 italic',
        )}>
          {value || 'No detectado'}
        </p>
      </div>
      {badge && <div className="shrink-0 mt-1">{badge}</div>}
    </div>
  );
}

function SourceBadge({ parseStatus }: { parseStatus: FiscalDocument['parse_status'] }) {
  const configs: Record<string, { bg: string; text: string; icon: React.ReactNode }> = {
    parsed: { bg: 'bg-indigo-50 border-indigo-200', text: 'text-indigo-600', icon: <Sparkles className="h-3 w-3" /> },
    manual: { bg: 'bg-slate-50 border-slate-200', text: 'text-slate-600', icon: <Pencil className="h-3 w-3" /> },
    pending: { bg: 'bg-sky-50 border-sky-200', text: 'text-sky-600', icon: <ScanLine className="h-3 w-3" /> },
    failed: { bg: 'bg-amber-50 border-amber-200', text: 'text-amber-600', icon: <ScanLine className="h-3 w-3" /> },
  };
  const fallback = { bg: 'bg-slate-50 border-slate-200', text: 'text-slate-500', icon: <ScanLine className="h-3 w-3" /> };
  const cfg = configs[parseStatus ?? ''] ?? fallback;
  return (
    <span className={cn(
      'inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-md border',
      cfg.bg, cfg.text,
    )}>
      {cfg.icon}
      {parseStatusLabel(parseStatus)}
    </span>
  );
}

export function ExtractionSummary({ document: doc, className }: ExtractionSummaryProps) {
  if (!doc) {
    return (
      <div className={cn(
        'rounded-xl border border-slate-200 bg-white p-5',
        className,
      )}>
        <h4 className="text-sm font-bold text-slate-800 mb-3 flex items-center gap-2">
          <ScanLine className="h-4 w-4 text-slate-400" aria-hidden="true" />
          Datos del comprobante
        </h4>
        <div className="flex flex-col items-center justify-center py-6 text-center">
          <FileText className="h-8 w-8 text-slate-300 mb-2" aria-hidden="true" />
          <p className="text-sm text-slate-500">Sin comprobante para analizar</p>
        </div>
      </div>
    );
  }

  const typeLabel = doc.document_subtype
    ?? ({
      factura: 'Factura',
      recibo: 'Recibo',
      ticket: 'Ticket',
      nota_credito: 'Nota de Crédito',
      nota_debito: 'Nota de Débito',
      otro: 'Otro',
    }[doc.document_type] ?? doc.document_type);

  const formattedDate = doc.issue_date
    ? format(parseISO(doc.issue_date), "d 'de' MMMM 'de' yyyy", { locale: es })
    : null;

  return (
    <div className={cn(
      'rounded-xl border border-slate-200 bg-white',
      className,
    )}>
      <div className="flex items-center justify-between px-5 pt-4 pb-2">
        <h4 className="text-sm font-bold text-slate-800 flex items-center gap-2">
          <ScanLine className="h-4 w-4 text-slate-400" aria-hidden="true" />
          Datos del comprobante
        </h4>
        <SourceBadge parseStatus={doc.parse_status} />
      </div>

      <div className="px-5 pb-4">
        <FieldRow
          icon={<FileText className="h-4 w-4" />}
          label="Tipo de comprobante"
          value={typeLabel}
          badge={
            doc.is_fiscal_document ? (
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-md border border-emerald-200">
                Fiscal
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-[11px] font-medium bg-slate-50 text-slate-500 px-2 py-0.5 rounded-md border border-slate-200">
                No fiscal
              </span>
            )
          }
        />
        <FieldRow
          icon={<Hash className="h-4 w-4" />}
          label="Número de comprobante"
          value={doc.invoice_number || null}
        />
        {doc.point_of_sale && (
          <FieldRow
            icon={<CreditCard className="h-4 w-4" />}
            label="Punto de venta"
            value={doc.point_of_sale}
          />
        )}
        <FieldRow
          icon={<Calendar className="h-4 w-4" />}
          label="Fecha de emisión"
          value={formattedDate}
        />
        <FieldRow
          icon={<Building2 className="h-4 w-4" />}
          label="Emisor"
          value={doc.issuer_name || null}
        />
        <FieldRow
          icon={<Hash className="h-4 w-4" />}
          label="CUIT Emisor"
          value={doc.issuer_tax_id || null}
        />
        <FieldRow
          icon={<User className="h-4 w-4" />}
          label="CUIT Comprador"
          value={doc.buyer_tax_id || null}
        />
        {doc.buyer_name && (
          <FieldRow
            icon={<User className="h-4 w-4" />}
            label="Comprador"
            value={doc.buyer_name}
          />
        )}
        <FieldRow
          icon={<DollarSign className="h-4 w-4" />}
          label="Total detectado"
          value={
            doc.total
              ? `$${parseFloat(doc.total).toLocaleString('es-AR', { minimumFractionDigits: 2 })}`
              : null
          }
        />
        <FieldRow
          icon={<DollarSign className="h-4 w-4" />}
          label="Moneda"
          value={doc.currency || null}
        />
      </div>
    </div>
  );
}
