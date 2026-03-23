"use client";

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  CreditCard,
  Activity,
  AlertTriangle,
  Clock,
  TrendingDown,
  Pause,
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
  providerLabel,
  eventTypeLabel,
  formatDate,
  formatRelativeTime,
} from '@/lib/admin/display';
import type {
  AdminSubscriptionList,
  AdminSubscriptionRow,
  AdminSubscriptionKPIs,
} from '@/lib/admin/types';

type Props = {
  initialData: AdminSubscriptionList | null;
  kpis: AdminSubscriptionKPIs | null;
  initialParams: Record<string, string>;
};

export function SuscripcionesContent({ initialData, kpis, initialParams }: Props) {
  const router = useRouter();

  const [search, setSearch] = useState(initialParams.search ?? '');
  const [statusFilter, setStatusFilter] = useState(initialParams.status ?? '');
  const [paymentIssue, setPaymentIssue] = useState(initialParams.payment_issue ?? '');

  const currentPage = initialData?.page ?? 1;
  const totalPages = initialData?.total_pages ?? 1;

  const navigateWithParams = useCallback(
    (overrides: Record<string, string>) => {
      const params = new URLSearchParams();
      const merged = {
        search,
        status: statusFilter,
        payment_issue: paymentIssue,
        ...overrides,
      };
      for (const [k, v] of Object.entries(merged)) {
        if (v) params.set(k, v);
      }
      router.push(`/admin/suscripciones?${params.toString()}`);
    },
    [search, statusFilter, paymentIssue, router],
  );

  const handleSearchSubmit = useCallback(() => {
    navigateWithParams({ search, page: '1' });
  }, [search, navigateWithParams]);

  const columns: DataTableColumn<AdminSubscriptionRow>[] = [
    {
      key: 'business_name',
      header: 'Cliente',
      render: (row) => (
        <div>
          <p className="font-medium text-slate-900">{row.business_name}</p>
          <p className="text-xs text-slate-500">ID: {row.business_id}</p>
        </div>
      ),
    },
    {
      key: 'plan_code',
      header: 'Plan',
      render: (row) => <span className="text-sm">{planLabel(row.plan_code)}</span>,
    },
    {
      key: 'admin_status',
      header: 'Estado',
      render: (row) => (
        <StatusBadge label={statusLabel(row.admin_status)} colorClass={statusColor(row.admin_status)} />
      ),
    },
    {
      key: 'provider',
      header: 'Provider',
      render: (row) => <span className="text-sm">{providerLabel(row.provider)}</span>,
    },
    {
      key: 'current_period_end',
      header: 'Renovación',
      render: (row) => <span className="text-sm">{formatDate(row.current_period_end)}</span>,
    },
    {
      key: 'retry_count',
      header: 'Reintentos',
      className: 'text-center',
      render: (row) => (
        <span className={`text-sm ${row.retry_count > 0 ? 'font-medium text-amber-600' : 'text-slate-400'}`}>
          {row.retry_count}
        </span>
      ),
    },
    {
      key: 'last_event',
      header: 'Último evento',
      render: (row) =>
        row.last_event ? (
          <div>
            <p className="text-xs font-medium text-slate-700">{eventTypeLabel(row.last_event.event_type)}</p>
            <p className="text-xs text-slate-500">{formatRelativeTime(row.last_event.received_at)}</p>
          </div>
        ) : (
          <span className="text-xs text-slate-400">—</span>
        ),
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
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-8">
          <StatCard title="Total" value={kpis.total} icon={CreditCard} />
          <StatCard title="Activas" value={kpis.active} icon={Activity} />
          <StatCard title="En prueba" value={kpis.trialing} icon={Clock} />
          <StatCard
            title="Pago vencido"
            value={kpis.past_due}
            icon={AlertTriangle}
            className={kpis.past_due > 0 ? 'border-amber-200 bg-amber-50' : undefined}
          />
          <StatCard
            title="Suspendidas"
            value={kpis.suspended}
            icon={Pause}
            className={kpis.suspended > 0 ? 'border-red-200 bg-red-50' : undefined}
          />
          <StatCard title="Canceladas" value={kpis.canceled} icon={TrendingDown} />
          <StatCard
            title="Cancel. programada"
            value={kpis.scheduled_cancel}
            icon={TrendingDown}
            className={kpis.scheduled_cancel > 0 ? 'border-orange-200 bg-orange-50' : undefined}
          />
          <StatCard title="Checkout pend." value={kpis.checkout_pending} icon={CreditCard} />
        </div>
      )}

      {/* Filters */}
      <FilterBar
        searchValue={search}
        onSearchChange={setSearch}
        searchPlaceholder="Buscar por cliente, email, ID de suscripción o provider ID..."
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
              { label: 'Activa', value: 'active' },
              { label: 'En prueba', value: 'trialing' },
              { label: 'Pago vencido', value: 'past_due' },
              { label: 'Suspendida', value: 'suspended' },
              { label: 'Cancelada', value: 'canceled' },
              { label: 'Checkout pendiente', value: 'checkout_pending' },
              { label: 'Cancelación programada', value: 'scheduled_cancel' },
            ],
          },
          {
            key: 'payment_issue',
            label: 'Pago',
            value: paymentIssue,
            onChange: (v) => {
              setPaymentIssue(v);
              navigateWithParams({ payment_issue: v, page: '1' });
            },
            options: [
              { label: 'Con problemas', value: 'true' },
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
        data={(initialData?.results ?? []) as (AdminSubscriptionRow & Record<string, unknown>)[]}
        keyExtractor={(row) => row.id}
        loading={false}
        error={initialData === null ? 'No se pudieron cargar las suscripciones.' : null}
        emptyTitle="Sin suscripciones"
        emptyDescription="No se encontraron suscripciones con los filtros seleccionados."
        onRowClick={(row) => router.push(`/admin/suscripciones/${row.id}`)}
      />

      {/* Pagination */}
      {initialData && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-slate-500">
            {initialData.total} suscripción{initialData.total !== 1 ? 'es' : ''} en total
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
