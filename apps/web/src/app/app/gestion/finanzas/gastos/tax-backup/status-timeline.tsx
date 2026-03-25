"use client";

import { format } from 'date-fns';
import { es } from 'date-fns/locale';
import type { StatusLog } from '@/lib/api/tax-backup';
import { cn } from '@/lib/utils';
import { TAX_STATUS_CONFIG } from './constants';

function StatusBadgeInline({ status }: { status: string }) {
  const config =
    TAX_STATUS_CONFIG[status as keyof typeof TAX_STATUS_CONFIG] ??
    TAX_STATUS_CONFIG.registrado;
  return (
    <span
      className={cn(
        'text-xs px-2 py-0.5 rounded-full font-medium',
        config.bg,
        config.text,
      )}
    >
      {config.label}
    </span>
  );
}

interface Props {
  logs: StatusLog[];
}

export function StatusTimeline({ logs }: Props) {
  if (!logs.length) {
    return (
      <p className="text-sm text-slate-400 py-4 text-center">
        Sin cambios de estado registrados
      </p>
    );
  }

  const sorted = [...logs].sort(
    (a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  return (
    <div className="space-y-0">
      {sorted.map((log, i) => (
        <div key={log.id} className="flex gap-3">
          <div className="flex flex-col items-center">
            <div
              className={cn(
                'w-2.5 h-2.5 rounded-full mt-1.5 shrink-0',
                i === 0 ? 'bg-slate-900' : 'bg-slate-300',
              )}
            />
            {i < sorted.length - 1 && (
              <div className="w-px flex-1 bg-slate-200 mt-1" />
            )}
          </div>
          <div className="pb-4 min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <StatusBadgeInline status={log.previous_status} />
              <span className="text-slate-400 text-xs">→</span>
              <StatusBadgeInline status={log.new_status} />
            </div>
            <p className="text-xs text-slate-500 mt-1">
              {format(new Date(log.created_at), 'dd/MM/yyyy HH:mm', {
                locale: es,
              })}
              {log.rule_code && (
                <>
                  {' · Regla: '}
                  <code className="text-xs bg-slate-100 px-1 rounded">
                    {log.rule_code}
                  </code>
                </>
              )}
            </p>
            {log.note && (
              <p className="text-xs text-slate-400 mt-0.5 italic">{log.note}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
