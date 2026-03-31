'use client';

import { useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  Bug,
  Server,
  Clock,
  AlertTriangle,
  Hash,
} from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';
import { cn } from '@/lib/utils';
import type { FiscalProfileDetail, FiscalDocument } from '@/lib/api/tax-backup';

interface TechnicalTraceProps {
  profile: FiscalProfileDetail;
  document: FiscalDocument | null;
  className?: string;
}

interface TraceRow {
  label: string;
  value: string | null | undefined;
  icon: React.ReactNode;
}

export function TechnicalTrace({ profile, document: doc, className }: TechnicalTraceProps) {
  const [isOpen, setIsOpen] = useState(false);

  const rows: TraceRow[] = [
    {
      label: 'Estado fiscal (tax_status)',
      value: `${profile.tax_status} — ${profile.tax_status_display}`,
      icon: <Server className="h-3.5 w-3.5" />,
    },
    {
      label: 'Estado documental (fiscal_status)',
      value: `${profile.fiscal_status} — ${profile.fiscal_status_display}`,
      icon: <Server className="h-3.5 w-3.5" />,
    },
    {
      label: 'Fuente de evaluación',
      value: profile.evaluation_source,
      icon: <Hash className="h-3.5 w-3.5" />,
    },
    {
      label: 'Última evaluación',
      value: profile.evaluated_at
        ? format(parseISO(profile.evaluated_at), "d MMM yyyy, HH:mm", { locale: es })
        : 'No evaluado',
      icon: <Clock className="h-3.5 w-3.5" />,
    },
    {
      label: 'Motivo de revisión',
      value: profile.review_reason || 'Sin motivo',
      icon: <AlertTriangle className="h-3.5 w-3.5" />,
    },
    {
      label: 'Profile ID',
      value: String(profile.id),
      icon: <Hash className="h-3.5 w-3.5" />,
    },
  ];

  if (doc) {
    rows.push(
      {
        label: 'Document ID',
        value: String(doc.id),
        icon: <Hash className="h-3.5 w-3.5" />,
      },
      {
        label: 'Estado de extracción (parse_status)',
        value: doc.parse_status,
        icon: <Server className="h-3.5 w-3.5" />,
      },
      {
        label: 'Fecha de carga',
        value: format(parseISO(doc.created_at), "d MMM yyyy, HH:mm", { locale: es }),
        icon: <Clock className="h-3.5 w-3.5" />,
      },
    );
  }

  // Validation issues
  const issues = profile.validation_issues ?? [];
  const missingFields = profile.missing_fields ?? [];

  return (
    <div className={cn('rounded-xl border border-slate-200 bg-white', className)}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-between w-full px-5 py-3 text-sm font-bold text-slate-600 hover:text-slate-800 transition-colors"
        aria-expanded={isOpen}
        aria-controls="technical-trace-content"
      >
        <span className="flex items-center gap-2">
          <Bug className="h-4 w-4 text-slate-400" aria-hidden="true" />
          Detalle técnico
        </span>
        {isOpen ? (
          <ChevronUp className="h-4 w-4 text-slate-400" />
        ) : (
          <ChevronDown className="h-4 w-4 text-slate-400" />
        )}
      </button>

      {isOpen && (
        <div id="technical-trace-content" className="px-5 pb-4 space-y-3">
          {/* Trace rows */}
          <div className="space-y-1">
            {rows.map((row) => (
              <div
                key={row.label}
                className="flex items-start gap-2 py-1.5 text-xs"
              >
                <span className="text-slate-400 mt-0.5 shrink-0">{row.icon}</span>
                <span className="font-medium text-slate-500 min-w-[160px] shrink-0">
                  {row.label}
                </span>
                <span className="text-slate-700 font-mono break-all">
                  {row.value || '—'}
                </span>
              </div>
            ))}
          </div>

          {/* Validation issues */}
          {issues.length > 0 && (
            <div className="pt-2 border-t border-slate-100">
              <p className="text-xs font-semibold text-slate-600 mb-1.5">
                Observaciones de validación ({issues.length})
              </p>
              <ul className="space-y-1">
                {issues.map((issue, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs">
                    <AlertTriangle className="h-3 w-3 text-amber-500 mt-0.5 shrink-0" aria-hidden="true" />
                    <span className="text-slate-600">
                      <code className="bg-slate-100 px-1 rounded text-[10px] font-mono mr-1">
                        {issue.code}
                      </code>
                      {issue.message}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Missing fields */}
          {missingFields.length > 0 && (
            <div className="pt-2 border-t border-slate-100">
              <p className="text-xs font-semibold text-slate-600 mb-1.5">
                Campos faltantes (missing_fields)
              </p>
              <div className="flex flex-wrap gap-1">
                {missingFields.map((f) => (
                  <code
                    key={f}
                    className="text-[10px] font-mono bg-rose-50 text-rose-600 px-1.5 py-0.5 rounded border border-rose-200"
                  >
                    {f}
                  </code>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
