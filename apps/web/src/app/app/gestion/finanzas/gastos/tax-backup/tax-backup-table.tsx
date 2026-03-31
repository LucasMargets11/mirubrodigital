"use client";

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Search, Eye } from 'lucide-react';

import {
  listProfiles,
  taxBackupKeys,
  safeAmount,
  type FiscalProfile,
  type TaxStatus,
  type AllocationType,
  type FiscalStatus,
} from '@/lib/api/tax-backup';
import { Currency } from '../../components/currency';
import { cn } from '@/lib/utils';
import { TAX_STATUS_CONFIG, FISCAL_STATUS_CONFIG, ALLOCATION_CONFIG, PAGE_SIZE } from './constants';

interface Props {
  selectedId: number | null;
  onSelect: (id: number) => void;
  compact?: boolean;
}

export function TaxBackupTable({ selectedId, onSelect, compact = false }: Props) {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<TaxStatus | ''>('');
  const [allocationFilter, setAllocationFilter] = useState<
    AllocationType | ''
  >('');

  const offset = (page - 1) * PAGE_SIZE;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: taxBackupKeys.profiles({
      limit: String(PAGE_SIZE),
      offset: String(offset),
      search: search || undefined,
      tax_status: statusFilter || undefined,
      allocation_type: allocationFilter || undefined,
    }),
    queryFn: () =>
      listProfiles({
        limit: PAGE_SIZE,
        offset,
        search: search || undefined,
        tax_status: statusFilter || undefined,
        allocation_type: allocationFilter || undefined,
      }),
  });

  const profiles = data?.results ?? [];
  const total = data?.count ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function handleSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    setPage(1);
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-center">
        <p className="text-sm text-slate-500 mb-3">
          Error al cargar los perfiles
        </p>
        <button
          onClick={() => refetch()}
          className="text-sm text-indigo-600 hover:text-indigo-700 font-medium"
        >
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-col md:flex-row gap-3">
        <form onSubmit={handleSearchSubmit} className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Buscar por nombre de gasto..."
            className="block w-full rounded-lg border border-slate-300 pl-9 pr-3 py-2 text-sm focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400"
          />
        </form>
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value as TaxStatus | '');
            setPage(1);
          }}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="">Todos los estados</option>
          {Object.entries(TAX_STATUS_CONFIG).map(([key, cfg]) => (
            <option key={key} value={key}>
              {cfg.label}
            </option>
          ))}
        </select>
        <select
          value={allocationFilter}
          onChange={(e) => {
            setAllocationFilter(e.target.value as AllocationType | '');
            setPage(1);
          }}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="">Todas las asignaciones</option>
          {Object.entries(ALLOCATION_CONFIG).map(([key, cfg]) => (
            <option key={key} value={key}>
              {cfg.label}
            </option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 text-left text-xs font-medium uppercase tracking-wider text-slate-500">
              <th className="px-3 py-2.5">Gasto</th>
              {!compact && <th className="px-3 py-2.5">Monto</th>}
              <th className="px-3 py-2.5">Estado</th>
              {!compact && <th className="px-3 py-2.5">Fiscal</th>}
              {!compact && <th className="px-3 py-2.5">Asignación</th>}
              {!compact && <th className="px-3 py-2.5 text-center">Docs</th>}
              {!compact && <th className="px-3 py-2.5 text-right">Acción</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading
              ? Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}>
                    <td colSpan={compact ? 2 : 7} className="px-3 py-3">
                      <div className="h-4 w-full animate-pulse rounded bg-slate-100" />
                    </td>
                  </tr>
                ))
              : profiles.map((p: FiscalProfile) => {
                  const statusCfg = TAX_STATUS_CONFIG[p.tax_status];
                  const fiscalCfg = FISCAL_STATUS_CONFIG[p.fiscal_status];
                  const allocCfg = ALLOCATION_CONFIG[p.allocation_type];
                  const isSelected = selectedId === p.id;
                  return (
                    <tr
                      key={p.id}
                      onClick={() => onSelect(p.id)}
                      className={cn(
                        'cursor-pointer transition-colors',
                        isSelected
                          ? 'bg-indigo-50 border-l-2 border-l-indigo-500'
                          : 'hover:bg-slate-50/70 border-l-2 border-l-transparent',
                      )}
                      aria-selected={isSelected}
                    >
                      <td className="px-3 py-2.5">
                        <div className="flex items-center gap-1.5 min-w-0">
                          {p.source_type === 'fixed_expense_period' && (
                            <span className="text-[10px] font-semibold text-violet-600 bg-violet-50 px-1 py-0.5 rounded border border-violet-200 shrink-0">Fijo</span>
                          )}
                          <span className={cn(
                            'font-medium truncate',
                            isSelected ? 'text-indigo-900' : 'text-slate-800',
                          )}>
                            {p.source_name || 'Sin nombre'}
                          </span>
                        </div>
                        {compact && p.source_amount != null && (
                          <span className="text-xs font-mono text-slate-500 mt-0.5 block">
                            <Currency amount={safeAmount(p.source_amount)} />
                          </span>
                        )}
                      </td>
                      {!compact && (
                        <td className="px-3 py-2.5 font-mono text-slate-700 tabular-nums">
                          {p.source_amount != null
                            ? <Currency amount={safeAmount(p.source_amount)} />
                            : <span className="text-slate-400">—</span>}
                        </td>
                      )}
                      <td className="px-3 py-2.5">
                        <span
                          className={cn(
                            'inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold border',
                            statusCfg.bg,
                            statusCfg.text,
                            statusCfg.border,
                          )}
                        >
                          {compact ? statusCfg.shortLabel : statusCfg.label}
                        </span>
                      </td>
                      {!compact && fiscalCfg && (
                        <td className="px-3 py-2.5">
                          <span
                            className={cn(
                              'inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold border',
                              fiscalCfg.bg,
                              fiscalCfg.text,
                              fiscalCfg.border,
                            )}
                          >
                            {fiscalCfg.shortLabel}
                          </span>
                        </td>
                      )}
                      {!compact && !fiscalCfg && (
                        <td className="px-3 py-2.5 text-xs text-slate-400">—</td>
                      )}
                      {!compact && (
                        <td className="px-3 py-2.5 text-slate-600 text-xs">
                          {allocCfg.icon} {allocCfg.label}
                        </td>
                      )}
                      {!compact && (
                        <td className="px-3 py-2.5 text-center text-slate-500">
                          {p.doc_count}
                        </td>
                      )}
                      {!compact && (
                        <td className="px-3 py-2.5 text-right">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onSelect(p.id);
                            }}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-700 bg-indigo-50 hover:bg-indigo-100 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1"
                            aria-label={`Revisar comprobante de ${p.source_name || 'gasto'}`}
                          >
                            <Eye className="h-3.5 w-3.5" />
                            Revisar
                          </button>
                        </td>
                      )}
                    </tr>
                  );
                })}
            {!isLoading && profiles.length === 0 && (
              <tr>
                <td
                  colSpan={compact ? 2 : 7}
                  className="px-4 py-12 text-center text-slate-400"
                >
                  No se encontraron perfiles con estos filtros.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Classic pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-slate-500">
          <span>
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} de {total}
          </span>
          <div className="flex gap-1">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="h-4 w-4" />
              Anterior
            </button>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Siguiente
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
