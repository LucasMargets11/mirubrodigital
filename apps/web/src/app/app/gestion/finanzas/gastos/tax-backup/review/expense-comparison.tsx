'use client';

import { CheckCircle2, XCircle, AlertCircle, Minus } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ComparisonField } from './view-models';

interface ExpenseComparisonProps {
  fields: ComparisonField[];
  className?: string;
}

function MatchIcon({ matches }: { matches: boolean | null }) {
  if (matches === true) {
    return (
      <span className="flex items-center gap-1 text-emerald-600" aria-label="Coincide">
        <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
        <span className="text-xs font-semibold">Coincide</span>
      </span>
    );
  }
  if (matches === false) {
    return (
      <span className="flex items-center gap-1 text-rose-600" aria-label="No coincide">
        <XCircle className="h-4 w-4" aria-hidden="true" />
        <span className="text-xs font-semibold">No coincide</span>
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-slate-400" aria-label="Sin datos para comparar">
      <Minus className="h-4 w-4" aria-hidden="true" />
      <span className="text-xs font-medium">Sin datos</span>
    </span>
  );
}

export function ExpenseComparison({ fields, className }: ExpenseComparisonProps) {
  const matchCount = fields.filter((f) => f.matches === true).length;
  const mismatchCount = fields.filter((f) => f.matches === false).length;
  const unknownCount = fields.filter((f) => f.matches === null).length;

  return (
    <div className={cn('rounded-xl border border-slate-200 bg-white', className)}>
      <div className="px-5 pt-4 pb-2">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-bold text-slate-800 flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-slate-400" aria-hidden="true" />
            Gasto vs Comprobante
          </h4>
          <div className="flex items-center gap-2">
            {matchCount > 0 && (
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-full border border-emerald-200">
                <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                {matchCount}
              </span>
            )}
            {mismatchCount > 0 && (
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold bg-rose-50 text-rose-700 px-2 py-0.5 rounded-full border border-rose-200">
                <XCircle className="h-3 w-3" aria-hidden="true" />
                {mismatchCount}
              </span>
            )}
            {unknownCount > 0 && (
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold bg-slate-50 text-slate-500 px-2 py-0.5 rounded-full border border-slate-200">
                <Minus className="h-3 w-3" aria-hidden="true" />
                {unknownCount}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="px-5 pb-4 overflow-x-auto">
        {/* Table header — hidden on mobile, stacked layout used instead */}
        <div className="hidden sm:grid grid-cols-[1fr_1fr_1fr_auto] gap-3 px-3 py-2 text-xs font-medium uppercase tracking-wider text-slate-400 border-b border-slate-100">
          <span>Campo</span>
          <span>Esperado</span>
          <span>Detectado</span>
          <span className="text-right">Estado</span>
        </div>

        {/* Rows */}
        {fields.map((field) => (
          <div
            key={field.key}
            className={cn(
              'sm:grid sm:grid-cols-[1fr_1fr_1fr_auto] gap-2 sm:gap-3 px-3 py-3 border-b border-slate-50 last:border-0 items-start sm:items-center transition-colors rounded-md',
              field.matches === false && 'bg-rose-50/50',
              field.matches === true && 'bg-emerald-50/30',
            )}
          >
            <span className="text-sm font-semibold text-slate-700 sm:font-medium">{field.label}</span>
            <div className="flex sm:block items-center gap-2 mt-1 sm:mt-0">
              <span className="text-xs text-slate-400 sm:hidden">Esperado:</span>
              <span className={cn(
                'text-sm',
                field.expected ? 'text-slate-600' : 'text-slate-400 italic',
              )}>
                {field.expected || '—'}
              </span>
            </div>
            <div className="flex sm:block items-center gap-2 mt-0.5 sm:mt-0">
              <span className="text-xs text-slate-400 sm:hidden">Detectado:</span>
              <span className={cn(
                'text-sm font-medium',
                field.detected ? 'text-slate-800' : 'text-slate-400 italic',
                field.matches === false && 'text-rose-700',
                field.matches === true && 'text-emerald-700',
              )}>
                {field.detected || 'No detectado'}
              </span>
            </div>
            <div className="text-right">
              <MatchIcon matches={field.matches} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
