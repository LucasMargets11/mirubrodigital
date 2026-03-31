'use client';

import { CheckCircle2, Circle } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { CompletionItem } from '@/lib/api/tax-backup';

interface CompletionChecklistProps {
  items: CompletionItem[];
  className?: string;
}

export function CompletionChecklist({ items, className }: CompletionChecklistProps) {
  const applicable = items.filter((i) => i.applicable);
  const done = applicable.filter((i) => i.done).length;
  const total = applicable.length;

  if (total === 0) return null;

  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  const allDone = done === total;

  return (
    <div className={cn('rounded-xl border border-slate-200 bg-white', className)}>
      <div className="px-5 pt-4 pb-2">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-bold text-slate-800">
            Qué falta completar
          </h4>
          <span
            className={cn(
              'text-xs font-bold px-2.5 py-0.5 rounded-full',
              allDone
                ? 'bg-emerald-100 text-emerald-700'
                : 'bg-slate-100 text-slate-600',
            )}
          >
            {done}/{total}
          </span>
        </div>

        {/* Progress bar */}
        <div
          className="w-full bg-slate-100 rounded-full h-2 mt-3"
          role="progressbar"
          aria-valuenow={done}
          aria-valuemax={total}
          aria-label={`${done} de ${total} completados`}
        >
          <div
            className={cn(
              'h-2 rounded-full transition-all duration-500',
              allDone ? 'bg-emerald-500' : 'bg-indigo-500',
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      <ul className="px-5 pb-4 mt-2 space-y-1" aria-label="Lista de verificación">
        {applicable.map((item) => (
          <li
            key={item.key}
            className={cn(
              'flex items-start gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors',
              item.done ? 'bg-emerald-50/60' : 'bg-slate-50',
            )}
          >
            {item.done ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-500 mt-0.5 shrink-0" aria-hidden="true" />
            ) : (
              <Circle className="h-4 w-4 text-slate-300 mt-0.5 shrink-0" aria-hidden="true" />
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
            <span className="sr-only">
              {item.done ? 'Completado' : 'Pendiente'}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
