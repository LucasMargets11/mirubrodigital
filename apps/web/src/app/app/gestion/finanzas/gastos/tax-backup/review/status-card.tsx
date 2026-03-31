'use client';

import {
  ShieldCheck,
  ShieldAlert,
  ShieldX,
  Clock,
  Loader2,
  ArrowRight,
  FileSearch,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  type OperationalStatus,
  OPERATIONAL_STATUS_MAP,
  type OperationalStatusInfo,
} from './view-models';

interface StatusCardProps {
  status: OperationalStatus;
  nextAction?: string | null;
  className?: string;
}

function StatusIcon({ status, className }: { status: OperationalStatus; className?: string }) {
  const info = OPERATIONAL_STATUS_MAP[status];
  const iconClass = cn('h-6 w-6', className);
  switch (info.priority) {
    case 'success':
      return <ShieldCheck className={cn(iconClass, info.text)} />;
    case 'warning':
      return <ShieldAlert className={cn(iconClass, info.text)} />;
    case 'danger':
      return <ShieldX className={cn(iconClass, info.text)} />;
    case 'processing':
      return <Loader2 className={cn(iconClass, info.text, 'animate-spin')} />;
    default:
      return <FileSearch className={cn(iconClass, info.text)} />;
  }
}

export function StatusCard({ status, nextAction, className }: StatusCardProps) {
  const info = OPERATIONAL_STATUS_MAP[status];

  return (
    <div
      className={cn(
        'rounded-xl border-2 p-4',
        info.border,
        info.bg,
        className,
      )}
      role="status"
      aria-label={`Estado: ${info.label}`}
    >
      <div className="flex items-start gap-3">
        <div className={cn('p-2.5 rounded-lg shrink-0', info.iconBg)}>
          <StatusIcon status={status} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className={cn('text-lg font-bold', info.text)}>
            {info.label}
          </h3>
          <p className={cn('text-sm mt-1 leading-relaxed', info.text, 'opacity-80')}>
            {info.description}
          </p>
          {(nextAction || info.actionLabel) && (
            <div className="flex items-start gap-2 mt-3 p-2.5 bg-white/70 rounded-lg border border-white/50">
              <ArrowRight className={cn('h-4 w-4 mt-0.5 shrink-0', info.text)} aria-hidden="true" />
              <p className="text-sm font-medium text-slate-800">
                {nextAction || info.actionLabel}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
