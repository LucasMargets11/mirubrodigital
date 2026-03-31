'use client';

import {
  Upload,
  ScanLine,
  CheckCircle2,
  Pencil,
  RefreshCcw,
  Clock,
} from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';
import { cn } from '@/lib/utils';
import type { StatusLog, TaxStatus } from '@/lib/api/tax-backup';
import { TAX_STATUS_CONFIG } from '../constants';

interface ReviewTimelineProps {
  logs: StatusLog[];
  documentCreatedAt?: string | null;
  className?: string;
}

interface TimelineEvent {
  id: string;
  icon: React.ReactNode;
  iconBg: string;
  title: string;
  subtitle?: string;
  timestamp: string;
}

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

export function ReviewTimeline({ logs, documentCreatedAt, className }: ReviewTimelineProps) {
  // Build unified timeline from status logs and document events
  const events: TimelineEvent[] = [];

  // Document upload event
  if (documentCreatedAt) {
    events.push({
      id: 'doc-upload',
      icon: <Upload className="h-3.5 w-3.5" />,
      iconBg: 'bg-indigo-100 text-indigo-600',
      title: 'Comprobante subido',
      timestamp: documentCreatedAt,
    });
  }

  // Status log events
  for (const log of logs) {
    const newCfg = TAX_STATUS_CONFIG[log.new_status];
    const ruleLabel = RULE_LABELS[log.rule_code] || log.rule_code;

    events.push({
      id: `log-${log.id}`,
      icon: statusPriority(log.new_status) === 'success'
        ? <CheckCircle2 className="h-3.5 w-3.5" />
        : <RefreshCcw className="h-3.5 w-3.5" />,
      iconBg: cn(
        statusPriority(log.new_status) === 'success' && 'bg-emerald-100 text-emerald-600',
        statusPriority(log.new_status) === 'warning' && 'bg-amber-100 text-amber-600',
        statusPriority(log.new_status) === 'danger' && 'bg-rose-100 text-rose-600',
        statusPriority(log.new_status) === 'info' && 'bg-slate-100 text-slate-600',
      ),
      title: newCfg?.label ?? log.new_status,
      subtitle: `${ruleLabel}${log.note ? ` — ${log.note}` : ''}`,
      timestamp: log.created_at,
    });
  }

  // Sort by date descending (newest first)
  events.sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
  );

  if (events.length === 0) {
    return (
      <div className={cn('rounded-xl border border-slate-200 bg-white', className)}>
        <div className="px-5 pt-4 pb-2">
          <h4 className="text-sm font-bold text-slate-800 flex items-center gap-2">
            <Clock className="h-4 w-4 text-slate-400" aria-hidden="true" />
            Historial
          </h4>
        </div>
        <div className="flex flex-col items-center justify-center px-5 pb-5 py-4 text-center">
          <Clock className="h-6 w-6 text-slate-300 mb-1" aria-hidden="true" />
          <p className="text-sm text-slate-400">Sin eventos registrados</p>
        </div>
      </div>
    );
  }

  return (
    <div className={cn('rounded-xl border border-slate-200 bg-white', className)}>
      <div className="px-5 pt-4 pb-2">
        <h4 className="text-sm font-bold text-slate-800 flex items-center gap-2">
          <Clock className="h-4 w-4 text-slate-400" aria-hidden="true" />
          Historial
          <span className="text-xs font-normal text-slate-400">
            ({events.length})
          </span>
        </h4>
      </div>

      <div className="px-5 pb-4">
        <div className="space-y-0">
          {events.map((event, i) => (
            <div key={event.id} className="flex gap-3">
              <div className="flex flex-col items-center">
                <div className={cn(
                  'w-7 h-7 rounded-full flex items-center justify-center shrink-0',
                  event.iconBg,
                )}>
                  {event.icon}
                </div>
                {i < events.length - 1 && (
                  <div className="w-px flex-1 bg-slate-200 mt-1" />
                )}
              </div>
              <div className="pb-4 min-w-0 pt-0.5">
                <p className="text-sm font-medium text-slate-700">{event.title}</p>
                {event.subtitle && (
                  <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
                    {event.subtitle}
                  </p>
                )}
                <p className="text-xs text-slate-400 mt-0.5">
                  {format(parseISO(event.timestamp), "d MMM yyyy, HH:mm", {
                    locale: es,
                  })}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function statusPriority(status: TaxStatus): 'success' | 'warning' | 'danger' | 'info' {
  return TAX_STATUS_CONFIG[status]?.priority ?? 'info';
}
