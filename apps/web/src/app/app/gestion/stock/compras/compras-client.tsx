"use client";

import { useState, useDeferredValue } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import { es } from 'date-fns/locale';
import { Search, Plus, ShoppingCart, CheckCircle2, Ban, ChevronRight, Loader2 } from 'lucide-react';
import Link from 'next/link';

import { listReplenishments, StockReplenishmentList } from '@/lib/api/replenishment';
import { listAccounts } from '@/lib/api/treasury';
import { cn } from '@/lib/utils';

type FiltersState = {
  date_from: string;
  date_to: string;
  search: string;
  account_id: string;
};

function formatCurrency(value: string | number) {
  return Number(value).toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

export function ComprasClient({ canManage }: { canManage: boolean }) {
  const today = new Date();
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);

  const [filters, setFilters] = useState<FiltersState>({
    date_from: format(firstDay, 'yyyy-MM-dd'),
    date_to: format(today, 'yyyy-MM-dd'),
    search: '',
    account_id: '',
  });
  const deferredSearch = useDeferredValue(filters.search);

  const { data: replenishments, isLoading } = useQuery({
    queryKey: ['replenishments', { ...filters, search: deferredSearch }],
    queryFn: () =>
      listReplenishments({
        date_from: filters.date_from,
        date_to: filters.date_to,
        search: deferredSearch,
        account_id: filters.account_id || undefined,
      }),
  });

  const { data: accounts } = useQuery({
    queryKey: ['treasury', 'accounts'],
    queryFn: listAccounts,
  });

  const handleFilter = (key: keyof FiltersState, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const totalAmount = replenishments
    ?.filter((r) => r.status === 'posted')
    .reduce((sum, r) => sum + Number(r.total_amount), 0) ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Compras / Reposición</h1>
          <p className="text-sm text-slate-500 mt-0.5">Historial de reposiciones de stock</p>
        </div>
        {canManage && (
          <Link
            href="/app/gestion/stock/reponer"
            className="inline-flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-full text-sm font-semibold hover:bg-slate-700 transition-colors"
          >
            <Plus className="h-4 w-4" />
            Nueva reposición
          </Link>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-col md:flex-row gap-3 bg-white rounded-3xl border border-slate-200 p-4 shadow-sm">
        <input
          type="date"
          value={filters.date_from}
          onChange={(e) => handleFilter('date_from', e.target.value)}
          className="rounded-lg border border-slate-200 text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-slate-900"
        />
        <input
          type="date"
          value={filters.date_to}
          onChange={(e) => handleFilter('date_to', e.target.value)}
          className="rounded-lg border border-slate-200 text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-slate-900"
        />
        <select
          value={filters.account_id}
          onChange={(e) => handleFilter('account_id', e.target.value)}
          className="rounded-lg border border-slate-200 text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-slate-900"
        >
          <option value="">Todas las cuentas</option>
          {accounts?.map((a) => (
            <option key={a.id} value={a.id}>{a.name}</option>
          ))}
        </select>
        <div className="relative flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <input
            type="text"
            placeholder="Buscar proveedor o comprobante..."
            value={filters.search}
            onChange={(e) => handleFilter('search', e.target.value)}
            className="pl-9 w-full rounded-full border border-slate-200 text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-slate-900"
          />
        </div>
      </div>

      {/* Summary chip */}
      {!isLoading && replenishments && replenishments.length > 0 && (
        <div className="flex gap-4 text-sm">
          <span className="text-slate-500">
            <strong className="text-slate-900">{replenishments.filter((r) => r.status === 'posted').length}</strong> reposiciones confirmadas
          </span>
          <span className="font-mono font-semibold text-slate-900">
            Total: ${formatCurrency(totalAmount)}
          </span>
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="flex justify-center items-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
        </div>
      ) : !replenishments?.length ? (
        <div className="flex flex-col items-center py-16 text-center">
          <ShoppingCart className="h-10 w-10 text-slate-300 mb-3" />
          <p className="font-semibold text-slate-600">No hay reposiciones en este período</p>
          <p className="text-sm text-slate-400 mt-1">
            {canManage ? 'Usá "Nueva reposición" para registrar una compra de mercadería.' : 'No encontramos compras con los filtros seleccionados.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {replenishments.map((r) => (
            <ReplenishmentRow key={r.id} replenishment={r} />
          ))}
        </div>
      )}
    </div>
  );
}

function ReplenishmentRow({ replenishment: r }: { replenishment: StockReplenishmentList }) {
  const isVoided = r.status === 'voided';
  return (
    <Link
      href={`/app/gestion/stock/compras/${r.id}`}
      className={cn(
        'flex items-center justify-between gap-4 bg-white rounded-2xl border border-slate-200 p-4 shadow-sm hover:shadow-md transition-all group',
        isVoided && 'opacity-50'
      )}
    >
      <div className="flex items-center gap-4">
        <div className={cn('p-2.5 rounded-xl', isVoided ? 'bg-slate-100 text-slate-400' : 'bg-orange-100 text-orange-600')}>
          <ShoppingCart className="h-5 w-5" />
        </div>
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-slate-900">{r.supplier_name}</span>
            {r.invoice_number && (
              <span className="text-xs text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md font-mono">{r.invoice_number}</span>
            )}
            {isVoided ? (
              <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-slate-200 text-slate-500">Anulado</span>
            ) : (
              <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-emerald-100 text-emerald-700">Confirmado</span>
            )}
          </div>
          <div className="flex gap-3 text-xs text-slate-500 mt-1">
            <span>{format(new Date(r.occurred_at), "d 'de' MMMM yyyy", { locale: es })}</span>
            {r.account_name && <span>· {r.account_name}</span>}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span className={cn('text-lg font-bold font-mono', isVoided ? 'text-slate-400 line-through' : 'text-orange-600')}>
          ${formatCurrency(r.total_amount)}
        </span>
        <ChevronRight className="h-4 w-4 text-slate-300 group-hover:text-slate-600 transition-colors" />
      </div>
    </Link>
  );
}
