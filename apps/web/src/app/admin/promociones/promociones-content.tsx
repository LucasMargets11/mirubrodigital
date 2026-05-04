"use client";

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Plus, Tag } from 'lucide-react';

import { DataTable, type DataTableColumn } from '@/components/admin/data-table';
import { FilterBar } from '@/components/admin/filter-bar';
import { Pagination } from '@/components/admin/pagination';
import { StatusBadge } from '@/components/admin/status-badge';
import { formatDate } from '@/lib/admin/display';
import type { AdminPromoCodeList, AdminPromoCodeRow } from '@/lib/admin/types';

type Props = {
  initialData: AdminPromoCodeList | null;
  initialParams: Record<string, string>;
};

function discountLabel(row: AdminPromoCodeRow): string {
  if (row.discount_type === 'percent') {
    return `${row.discount_value}%`;
  }
  return `$${row.discount_value}`;
}

function activeLabel(active: boolean): string {
  return active ? 'Activo' : 'Inactivo';
}

function activeColor(active: boolean): string {
  return active ? 'bg-green-100 text-green-800' : 'bg-slate-100 text-slate-500';
}

export function PromocionesContent({ initialData, initialParams }: Props) {
  const router = useRouter();

  const [search, setSearch] = useState(initialParams.search ?? '');
  const [activeFilter, setActiveFilter] = useState(initialParams.active ?? '');

  const currentPage = initialData?.page ?? 1;
  const totalPages = initialData?.total_pages ?? 1;

  const navigateWithParams = useCallback(
    (overrides: Record<string, string>) => {
      const params = new URLSearchParams();
      const merged = { search, active: activeFilter, ...overrides };
      for (const [k, v] of Object.entries(merged)) {
        if (v) params.set(k, v);
      }
      router.push(`/admin/promociones?${params.toString()}`);
    },
    [search, activeFilter, router],
  );

  const handleSearchChange = useCallback(
    (val: string) => {
      setSearch(val);
      navigateWithParams({ search: val, page: '1' });
    },
    [navigateWithParams],
  );

  const columns: DataTableColumn<AdminPromoCodeRow>[] = [
    {
      key: 'code',
      header: 'Código',
      render: (row) => (
        <div>
          <p className="font-mono font-semibold text-slate-900">{row.code}</p>
          <p className="text-xs text-slate-500">{row.name}</p>
        </div>
      ),
    },
    {
      key: 'discount_type',
      header: 'Descuento',
      render: (row) => (
        <span className="text-sm font-medium">{discountLabel(row)}</span>
      ),
    },
    {
      key: 'duration_cycles',
      header: 'Ciclos',
      className: 'text-center',
      render: (row) => <span className="text-sm">{row.duration_cycles}</span>,
    },
    {
      key: 'redemptions_count',
      header: 'Usos activos',
      className: 'text-center',
      render: (row) => (
        <span className="text-sm">
          {row.redemptions_count}
          {row.max_redemptions !== null ? ` / ${row.max_redemptions}` : ''}
        </span>
      ),
    },
    {
      key: 'ends_at',
      header: 'Vence',
      render: (row) => (
        <span className="text-sm">{row.ends_at ? formatDate(row.ends_at) : '—'}</span>
      ),
    },
    {
      key: 'active',
      header: 'Estado',
      render: (row) => (
        <StatusBadge label={activeLabel(row.active)} colorClass={activeColor(row.active)} />
      ),
    },
    {
      key: 'id',
      header: '',
      render: (row) => (
        <button
          onClick={() => router.push(`/admin/promociones/${row.id}`)}
          className="text-xs text-blue-600 hover:underline"
        >
          Ver detalle
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-4">
        <FilterBar
          searchValue={search}
          onSearchChange={handleSearchChange}
          searchPlaceholder="Buscar por código o nombre..."
          filters={[
            {
              key: 'active',
              label: 'Estado',
              value: activeFilter,
              options: [
                { value: '', label: 'Todos' },
                { value: 'true', label: 'Activos' },
                { value: 'false', label: 'Inactivos' },
              ],
              onChange: (val) => {
                setActiveFilter(val);
                navigateWithParams({ active: val, page: '1' });
              },
            },
          ]}
        />
        <button
          onClick={() => router.push('/admin/promociones/nueva')}
          className="flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          <Plus className="h-4 w-4" />
          Nuevo código
        </button>
      </div>

      {/* Table */}
      {initialData && initialData.results.length > 0 ? (
        <>
          <DataTable columns={columns} data={initialData.results} keyExtractor={(r) => r.id} />
          <Pagination
            page={currentPage}
            totalPages={totalPages}
            onPageChange={(page) => navigateWithParams({ page: String(page) })}
          />
        </>
      ) : (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 py-16 text-center">
          <Tag className="mb-3 h-8 w-8 text-slate-400" />
          <p className="text-sm font-medium text-slate-600">No hay códigos promocionales</p>
          <p className="mt-1 text-xs text-slate-400">
            Creá el primer código haciendo clic en &quot;Nuevo código&quot;.
          </p>
        </div>
      )}
    </div>
  );
}
