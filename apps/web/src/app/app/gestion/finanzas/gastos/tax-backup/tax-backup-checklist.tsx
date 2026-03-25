"use client";

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  CheckCircle2,
  XCircle,
  Loader2,
  AlertCircle,
  ClipboardCheck,
  ShieldCheck,
} from 'lucide-react';

import {
  getChecklist,
  taxBackupChecklistKeys,
  type ExportParams,
  type TaxStatus,
  type ChecklistItem,
} from '@/lib/api/tax-backup';
import { cn } from '@/lib/utils';

import { TAX_STATUS_CONFIG } from './constants';

// ── Helpers ──────────────────────────────────────────────────────────────────

const MONTHS = [
  { value: 1, label: 'Enero' },
  { value: 2, label: 'Febrero' },
  { value: 3, label: 'Marzo' },
  { value: 4, label: 'Abril' },
  { value: 5, label: 'Mayo' },
  { value: 6, label: 'Junio' },
  { value: 7, label: 'Julio' },
  { value: 8, label: 'Agosto' },
  { value: 9, label: 'Septiembre' },
  { value: 10, label: 'Octubre' },
  { value: 11, label: 'Noviembre' },
  { value: 12, label: 'Diciembre' },
];

const CURRENT_YEAR = new Date().getFullYear();
const YEARS = Array.from({ length: 5 }, (_, i) => CURRENT_YEAR - i);

// ── Component ────────────────────────────────────────────────────────────────

export function TaxBackupChecklist() {
  const now = new Date();
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [year, setYear] = useState(now.getFullYear());

  const params: ExportParams = { month, year };

  const {
    data: checklist,
    isLoading,
    isError,
  } = useQuery({
    queryKey: taxBackupChecklistKeys.checklist(params),
    queryFn: () => getChecklist(params),
  });

  return (
    <div className="space-y-6">
      {/* ── Filters ──────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">
            Mes
          </label>
          <select
            value={month}
            onChange={(e) => setMonth(Number(e.target.value))}
            className="rounded-lg border border-slate-200 bg-white text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {MONTHS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-500 mb-1">
            Año
          </label>
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="rounded-lg border border-slate-200 bg-white text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {YEARS.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* ── Loading / Error ──────────────────────────────────────── */}
      {isLoading && (
        <div className="flex justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
        </div>
      )}

      {isError && (
        <div className="flex items-center gap-2 text-rose-600 bg-rose-50 rounded-lg px-4 py-3 text-sm">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          Error al cargar el checklist del período.
        </div>
      )}

      {/* ── Checklist result ─────────────────────────────────────── */}
      {checklist && (
        <div className="space-y-5">
          {/* Score header */}
          <div
            className={cn(
              'rounded-2xl p-6',
              checklist.ready
                ? 'bg-emerald-50 border border-emerald-200'
                : 'bg-amber-50 border border-amber-200',
            )}
          >
            <div className="flex items-center gap-3 mb-2">
              {checklist.ready ? (
                <ShieldCheck className="h-7 w-7 text-emerald-600" />
              ) : (
                <ClipboardCheck className="h-7 w-7 text-amber-600" />
              )}
              <div>
                <h3
                  className={cn(
                    'text-lg font-semibold',
                    checklist.ready ? 'text-emerald-800' : 'text-amber-800',
                  )}
                >
                  {checklist.ready
                    ? 'Período listo para enviar'
                    : 'Período con pendientes'}
                </h3>
                <p
                  className={cn(
                    'text-sm',
                    checklist.ready ? 'text-emerald-600' : 'text-amber-600',
                  )}
                >
                  {checklist.score}/{checklist.total} reglas cumplidas
                  {checklist.period && ` — ${checklist.period}`}
                </p>
              </div>
            </div>

            {/* Progress bar */}
            <div className="w-full bg-white/60 rounded-full h-2.5 mt-3">
              <div
                className={cn(
                  'h-2.5 rounded-full transition-all duration-500',
                  checklist.ready ? 'bg-emerald-500' : 'bg-amber-500',
                )}
                style={{
                  width: `${(checklist.score / checklist.total) * 100}%`,
                }}
              />
            </div>
          </div>

          {/* Checklist items */}
          <div className="space-y-3">
            {checklist.items.map((item) => (
              <ChecklistItemCard key={item.key} item={item} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Item card ────────────────────────────────────────────────────────────────

function ChecklistItemCard({ item }: { item: ChecklistItem }) {
  const hasIds = item.profile_ids && item.profile_ids.length > 0;

  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-xl border p-4 transition-colors',
        item.passed
          ? 'border-emerald-200 bg-emerald-50/50'
          : 'border-rose-200 bg-rose-50/50',
      )}
    >
      {item.passed ? (
        <CheckCircle2 className="h-5 w-5 text-emerald-500 mt-0.5 flex-shrink-0" />
      ) : (
        <XCircle className="h-5 w-5 text-rose-500 mt-0.5 flex-shrink-0" />
      )}
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            'text-sm font-medium',
            item.passed ? 'text-emerald-800' : 'text-rose-800',
          )}
        >
          {item.label}
        </p>
        <p
          className={cn(
            'text-xs mt-0.5',
            item.passed ? 'text-emerald-600' : 'text-rose-600',
          )}
        >
          {item.detail}
        </p>
        {hasIds && (
          <p className="text-xs text-slate-400 mt-1">
            {`IDs perfil: ${item.profile_ids!.slice(0, 10).join(', ')}${item.profile_ids!.length > 10 ? '…' : ''}`}
          </p>
        )}
      </div>
    </div>
  );
}
