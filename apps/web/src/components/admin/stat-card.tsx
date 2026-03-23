"use client";

import { cn } from '@/lib/utils';
import type { LucideIcon } from 'lucide-react';

type StatCardProps = {
  title: string;
  value: string | number;
  description?: string;
  icon?: LucideIcon;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string;
  loading?: boolean;
  className?: string;
};

function StatCardSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-4 w-24 rounded bg-slate-200" />
      <div className="h-8 w-16 rounded bg-slate-200" />
      <div className="h-3 w-32 rounded bg-slate-100" />
    </div>
  );
}

export function StatCard({
  title,
  value,
  description,
  icon: Icon,
  trend,
  trendValue,
  loading = false,
  className,
}: StatCardProps) {
  return (
    <div
      className={cn(
        'rounded-xl border border-slate-200 bg-white p-6 shadow-sm',
        className,
      )}
    >
      {loading ? (
        <StatCardSkeleton />
      ) : (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-slate-500">{title}</p>
            {Icon && (
              <div className="rounded-lg bg-slate-100 p-2">
                <Icon className="h-4 w-4 text-slate-600" />
              </div>
            )}
          </div>
          <div className="mt-3">
            <p className="text-3xl font-bold text-slate-900">{value}</p>
          </div>
          {(description || trendValue) && (
            <div className="mt-2 flex items-center gap-2">
              {trendValue && (
                <span
                  className={cn(
                    'text-xs font-medium',
                    trend === 'up' && 'text-emerald-600',
                    trend === 'down' && 'text-red-600',
                    trend === 'neutral' && 'text-slate-500',
                  )}
                >
                  {trendValue}
                </span>
              )}
              {description && (
                <span className="text-xs text-slate-500">{description}</span>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
