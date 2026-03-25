"use client";

import type { TaxBackupSummary } from '@/lib/api/tax-backup';
import { cn } from '@/lib/utils';
import { DASHBOARD_STAT_CARDS } from './constants';

interface Props {
  summary: TaxBackupSummary;
}

export function TaxBackupDashboard({ summary }: Props) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {DASHBOARD_STAT_CARDS.map((card) => {
        const count =
          card.key === 'total'
            ? summary.total
            : (summary.by_status[card.key] ?? 0);
        return (
          <div
            key={card.key}
            className={cn('rounded-2xl border p-4 text-center', card.cardClass)}
          >
            <div className="text-2xl font-bold font-mono">{count}</div>
            <div className={cn('text-xs font-medium mt-1', card.textClass)}>
              {card.label}
            </div>
          </div>
        );
      })}
    </div>
  );
}
