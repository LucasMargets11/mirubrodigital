'use client';

import {
  ArrowLeft,
  Download,
  Replace,
  Calendar,
  DollarSign,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { FiscalProfileDetail } from '@/lib/api/tax-backup';
import { safeAmount } from '@/lib/api/tax-backup';
import { Currency } from '../../../components/currency';
import { ALLOCATION_CONFIG } from '../constants';
import {
  type OperationalStatus,
  OPERATIONAL_STATUS_MAP,
} from './view-models';

interface ReviewHeaderProps {
  profile: FiscalProfileDetail;
  operationalStatus: OperationalStatus;
  onBack: () => void;
  onReplace?: () => void;
  onDownload?: () => void;
  className?: string;
}

export function ReviewHeader({
  profile,
  operationalStatus,
  onBack,
  onReplace,
  onDownload,
  className,
}: ReviewHeaderProps) {
  const allocCfg = ALLOCATION_CONFIG[profile.allocation_type];
  const opInfo = OPERATIONAL_STATUS_MAP[operationalStatus];

  return (
    <header
      className={cn(
        'bg-white border border-slate-200 rounded-xl shadow-sm',
        className,
      )}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3">
        {/* Top row: back + actions */}
        <div className="flex items-center justify-between gap-4">
          <button
            onClick={onBack}
            className="flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-800 transition-colors rounded-lg px-2 py-1 -ml-2 hover:bg-slate-50"
            aria-label="Volver a la bandeja de respaldo"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="hidden sm:inline">Volver a Respaldo</span>
            <span className="sm:hidden">Volver</span>
          </button>

          <div className="flex items-center gap-2">
            {onDownload && (
              <Button
                variant="outline"
                size="sm"
                onClick={onDownload}
                className="gap-1.5"
              >
                <Download className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Descargar</span>
              </Button>
            )}
            {onReplace && (
              <Button
                variant="outline"
                size="sm"
                onClick={onReplace}
                className="gap-1.5"
              >
                <Replace className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Reemplazar</span>
              </Button>
            )}
          </div>
        </div>

        {/* Main info */}
        <div className="mt-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold text-slate-900 truncate">
                {profile.source_name || 'Gasto sin nombre'}
              </h1>
              {profile.source_type === 'fixed_expense_period' ? (
                <span className="inline-flex items-center text-xs font-semibold text-violet-700 bg-violet-100 px-2 py-0.5 rounded-md border border-violet-200">
                  Fijo
                </span>
              ) : (
                <span className="inline-flex items-center text-xs font-semibold text-sky-700 bg-sky-50 px-2 py-0.5 rounded-md border border-sky-200">
                  Puntual
                </span>
              )}
            </div>

            {/* Meta row */}
            <div className="flex items-center gap-3 mt-1.5 flex-wrap text-sm">
              <span className="font-semibold text-slate-800 tabular-nums flex items-center gap-1">
                <DollarSign className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
                {profile.source_amount != null ? (
                  <Currency amount={safeAmount(profile.source_amount)} />
                ) : (
                  <span className="text-slate-400">Monto no disponible</span>
                )}
              </span>
              {profile.source_period_label && (
                <span className="flex items-center gap-1 text-slate-500">
                  <Calendar className="h-3.5 w-3.5" aria-hidden="true" />
                  {profile.source_period_label}
                </span>
              )}
              <span className="flex items-center gap-1 text-slate-500">
                {allocCfg.icon} {allocCfg.label}
              </span>
            </div>
          </div>

          {/* Operational status badge */}
          <div
            className={cn(
              'inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-semibold border shrink-0',
              opInfo.bg,
              opInfo.text,
              opInfo.border,
            )}
            role="status"
            aria-label={`Estado: ${opInfo.label}`}
          >
            <span
              className={cn(
                'w-2 h-2 rounded-full',
                opInfo.priority === 'success' && 'bg-emerald-500',
                opInfo.priority === 'warning' && 'bg-amber-500',
                opInfo.priority === 'danger' && 'bg-rose-500',
                opInfo.priority === 'processing' && 'bg-sky-500 animate-pulse',
                opInfo.priority === 'info' && 'bg-slate-400',
              )}
              aria-hidden="true"
            />
            {opInfo.label}
          </div>
        </div>
      </div>
    </header>
  );
}
