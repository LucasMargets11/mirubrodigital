"use client";

import { useCallback, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  Building2,
  FlaskConical,
  AlertTriangle,
  TrendingDown,
  CreditCard,
} from 'lucide-react';

import { StatCard } from '@/components/admin/stat-card';
import { DataTable, type DataTableColumn } from '@/components/admin/data-table';
import { FilterBar } from '@/components/admin/filter-bar';
import { Pagination } from '@/components/admin/pagination';
import { StatusBadge } from '@/components/admin/status-badge';
import {
  statusLabel,
  statusColor,
  riskLabel,
  riskColor,
  planLabel,
  formatDate,
} from '@/lib/admin/display';
import type { AdminClientList, AdminClientRow, AdminClientKPIs } from '@/lib/admin/types';

type Props = {
  initialData: AdminClientList | null;
  kpis: AdminClientKPIs | null;
  initialParams: Record<string, string>;
};

export function ClientesContent({ initialData, kpis, initialParams }: Props) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [search, setSearch] = useState(initialParams.search ?? '');
  const [statusFilter, setStatusFilter] = useState(initialParams.status ?? '');
  const [planFilter, setPlanFilter] = useState(initialParams.plan ?? '');
  const [trialFilter, setTrialFilter] = useState(initialParams.trial ?? '');

  const currentPage = initialData?.page ?? 1;
  const totalPages = initialData?.total_pages ?? 1;

  const navigateWithParams = useCallback(
    (overrides: Record<string, string>) => {
      const params = new URLSearchParams();
      const merged = {
        search,
        status: statusFilter,
        plan: planFilter,
        trial: trialFilter,
        ...overrides,
      };
      for (const [k, v] of Object.entries(merged)) {
        if (v) params.set(k, v);
      }
      router.push(`/admin/clientes?${params.toString()}`);
    },
    [search, statusFilter, planFilter, trialFilter, router],
  );

  const handleSearch = useCallback(
    (value: string) => {
      setSearch(value);
      // Debounce: navigate on Enter or after typing stops — use blur for simplicity
    },
    [],
  );

  const handleSearchSubmit = useCallback(() => {
    navigateWithParams({ search, page: '1' });
  }, [search, navigateWithParams]);

  const columns: DataTableColumn<AdminClientRow>[] = [
    {
      key: 'name',
      header: 'Negocio',
      render: (row) => (
        <div>
          <p className="font-medium text-slate-900">{row.name}</p>
          <p className="text-xs text-slate-500">{row.email || '—'}</p>
        </div>
      ),
    },
    {
      key: 'plan',
      header: 'Plan',
      render: (row) => (
        <span className="text-sm">{planLabel(row.plan)}</span>
      ),
    },
    {
      key: 'status',
      header: 'Estado',
      render: (row) => (
        <StatusBadge
          label={statusLabel(row.status)}
          colorClass={statusColor(row.status)}
        />
      ),
    },
    {
      key: 'subscription_status',
      header: 'Suscripción',
      render: (row) => (
        <StatusBadge
          label={statusLabel(row.subscription_status)}
          colorClass={statusColor(row.subscription_status)}
        />
      ),
    },
    {
      key: 'created_at',
      header: 'Alta',
      render: (row) => <span className="text-sm">{formatDate(row.created_at)}</span>,
    },
    {
      key: 'next_renewal',
      header: 'Renovación',
      render: (row) => <span className="text-sm">{formatDate(row.next_renewal)}</span>,
    },
    {
      key: 'user_count',
      header: 'Usuarios',
      className: 'text-center',
      render: (row) => <span className="text-sm">{row.user_count}</span>,
    },
    {
      key: 'risk_badges',
      header: 'Riesgo',
      render: (row) =>
        row.risk_badges.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {row.risk_badges.map((b) => (
              <StatusBadge key={b} label={riskLabel(b)} colorClass={riskColor(b)} />
            ))}
          </div>
        ) : (
          <span className="text-xs text-slate-400">—</span>
        ),
    },
  ];

  return (
    <div className="space-y-6">
      {/* KPIs */}
      {kpis && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
          <StatCard title="Total clientes" value={kpis.total_clients} icon={Building2} />
          <StatCard title="Activos" value={kpis.active} icon={Building2} />
          <StatCard title="En prueba" value={kpis.trialing} icon={FlaskConical} />
          <StatCard
            title="Pago vencido"
            value={kpis.past_due}
            icon={AlertTriangle}
            className={kpis.past_due > 0 ? 'border-amber-200 bg-amber-50' : undefined}
          />
          <StatCard
            title="Cancel. programada"
            value={kpis.scheduled_cancel}
            icon={TrendingDown}
            className={kpis.scheduled_cancel > 0 ? 'border-orange-200 bg-orange-50' : undefined}
          />
          <StatCard
            title="Problemas de pago (30d)"
            value={kpis.payment_issues_30d}
            icon={CreditCard}
            className={kpis.payment_issues_30d > 0 ? 'border-red-200 bg-red-50' : undefined}
          />
        </div>
      )}

      {/* Filters */}
      <FilterBar
        searchValue={search}
        onSearchChange={handleSearch}
        searchPlaceholder="Buscar por nombre, email, slug o ID..."
        filters={[
          {
            key: 'status',
            label: 'Estado',
            value: statusFilter,
            onChange: (v) => {
              setStatusFilter(v);
              navigateWithParams({ status: v, page: '1' });
            },
            options: [
              { label: 'Activo', value: 'active' },
              { label: 'En prueba', value: 'trialing' },
              { label: 'Pago vencido', value: 'past_due' },
              { label: 'Suspendido', value: 'suspended' },
              { label: 'Cancelado', value: 'canceled' },
              { label: 'Onboarding', value: 'onboarding' },
            ],
          },
          {
            key: 'trial',
            label: 'Trial',
            value: trialFilter,
            onChange: (v) => {
              setTrialFilter(v);
              navigateWithParams({ trial: v, page: '1' });
            },
            options: [
              { label: 'En trial', value: 'true' },
              { label: 'Pagos', value: 'false' },
            ],
          },
        ]}
        actions={
          <button
            onClick={handleSearchSubmit}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            Buscar
          </button>
        }
      />

      {/* Table */}
      <DataTable
        columns={columns}
        data={(initialData?.results ?? []) as (AdminClientRow & Record<string, unknown>)[]}
        keyExtractor={(row) => row.id}
        loading={false}
        error={initialData === null ? 'No se pudieron cargar los clientes.' : null}
        emptyTitle="Sin clientes"
        emptyDescription="No se encontraron negocios con los filtros seleccionados."
        onRowClick={(row) => router.push(`/admin/clientes/${row.id}`)}
      />

      {/* Pagination */}
      {initialData && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-slate-500">
            {initialData.total} cliente{initialData.total !== 1 ? 's' : ''} en total
          </p>
          <Pagination
            page={currentPage}
            totalPages={totalPages}
            onPageChange={(p) => navigateWithParams({ page: String(p) })}
          />
        </div>
      )}
    </div>
  );
}
