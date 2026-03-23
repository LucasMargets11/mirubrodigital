"use client";

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Ticket,
  AlertCircle,
  Clock,
  CheckCircle2,
  UserX,
  MessageSquare,
  Plus,
} from 'lucide-react';

import { StatCard } from '@/components/admin/stat-card';
import { DataTable, type DataTableColumn } from '@/components/admin/data-table';
import { FilterBar } from '@/components/admin/filter-bar';
import { Pagination } from '@/components/admin/pagination';
import { StatusBadge } from '@/components/admin/status-badge';
import {
  ticketStatusLabel,
  ticketStatusColor,
  ticketPriorityLabel,
  ticketPriorityColor,
  ticketCategoryLabel,
  formatRelativeTime,
} from '@/lib/admin/display';
import type {
  AdminTicketList,
  AdminTicketRow,
  AdminTicketKPIs,
} from '@/lib/admin/types';

type Props = {
  initialData: AdminTicketList | null;
  kpis: AdminTicketKPIs | null;
  initialParams: Record<string, string>;
};

export function SoporteContent({ initialData, kpis, initialParams }: Props) {
  const router = useRouter();

  const [search, setSearch] = useState(initialParams.search ?? '');
  const [statusFilter, setStatusFilter] = useState(initialParams.status ?? '');
  const [priorityFilter, setPriorityFilter] = useState(initialParams.priority ?? '');
  const [categoryFilter, setCategoryFilter] = useState(initialParams.category ?? '');
  const [assignedFilter, setAssignedFilter] = useState(initialParams.assigned_to ?? '');
  const [showCreate, setShowCreate] = useState(false);

  const currentPage = initialData?.page ?? 1;
  const totalPages = initialData?.total_pages ?? 1;

  const navigateWithParams = useCallback(
    (overrides: Record<string, string>) => {
      const params = new URLSearchParams();
      const merged = {
        search,
        status: statusFilter,
        priority: priorityFilter,
        category: categoryFilter,
        assigned_to: assignedFilter,
        ...overrides,
      };
      for (const [k, v] of Object.entries(merged)) {
        if (v) params.set(k, v);
      }
      router.push(`/admin/soporte?${params.toString()}`);
    },
    [search, statusFilter, priorityFilter, categoryFilter, assignedFilter, router],
  );

  const handleSearchSubmit = useCallback(() => {
    navigateWithParams({ search, page: '1' });
  }, [search, navigateWithParams]);

  const columns: DataTableColumn<AdminTicketRow>[] = [
    {
      key: 'reference',
      header: 'Ref.',
      render: (row) => (
        <span className="font-mono text-xs font-medium text-brand-600">{row.reference}</span>
      ),
    },
    {
      key: 'subject',
      header: 'Asunto',
      render: (row) => (
        <div className="max-w-xs">
          <p className="truncate font-medium text-slate-900">{row.subject}</p>
          <p className="text-xs text-slate-500">{row.business_name}</p>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Estado',
      render: (row) => (
        <StatusBadge label={ticketStatusLabel(row.status)} colorClass={ticketStatusColor(row.status)} />
      ),
    },
    {
      key: 'priority',
      header: 'Prioridad',
      render: (row) => (
        <StatusBadge label={ticketPriorityLabel(row.priority)} colorClass={ticketPriorityColor(row.priority)} />
      ),
    },
    {
      key: 'category',
      header: 'Categoría',
      render: (row) => <span className="text-sm">{ticketCategoryLabel(row.category)}</span>,
    },
    {
      key: 'assigned_to_name',
      header: 'Asignado',
      render: (row) =>
        row.assigned_to_name ? (
          <span className="text-sm">{row.assigned_to_name}</span>
        ) : (
          <span className="text-xs text-slate-400">Sin asignar</span>
        ),
    },
    {
      key: 'message_count',
      header: 'Msgs',
      className: 'text-center',
      render: (row) => (
        <div className="flex items-center justify-center gap-1 text-sm text-slate-600">
          <MessageSquare className="h-3.5 w-3.5" />
          {row.message_count}
        </div>
      ),
    },
    {
      key: 'updated_at',
      header: 'Actualizado',
      render: (row) => (
        <span className="text-xs text-slate-500">{formatRelativeTime(row.updated_at)}</span>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      {/* KPIs */}
      {kpis && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          <StatCard title="Total" value={kpis.total} icon={Ticket} />
          <StatCard
            title="Abiertos"
            value={kpis.open}
            icon={AlertCircle}
            className={kpis.open > 0 ? 'border-blue-200 bg-blue-50' : undefined}
          />
          <StatCard
            title="Urgentes"
            value={kpis.by_priority.urgent ?? 0}
            icon={AlertCircle}
            className={(kpis.by_priority.urgent ?? 0) > 0 ? 'border-red-200 bg-red-50' : undefined}
          />
          <StatCard
            title="Sin asignar"
            value={kpis.unassigned}
            icon={UserX}
            className={kpis.unassigned > 0 ? 'border-amber-200 bg-amber-50' : undefined}
          />
          <StatCard title="Resueltos" value={kpis.by_status.resolved ?? 0} icon={CheckCircle2} />
        </div>
      )}

      {/* Filters + Create button */}
      <FilterBar
        searchValue={search}
        onSearchChange={setSearch}
        searchPlaceholder="Buscar por referencia, asunto, cliente o email..."
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
              { label: 'Abierto', value: 'open' },
              { label: 'En curso', value: 'in_progress' },
              { label: 'Esperando cliente', value: 'waiting_on_client' },
              { label: 'Resuelto', value: 'resolved' },
              { label: 'Cerrado', value: 'closed' },
            ],
          },
          {
            key: 'priority',
            label: 'Prioridad',
            value: priorityFilter,
            onChange: (v) => {
              setPriorityFilter(v);
              navigateWithParams({ priority: v, page: '1' });
            },
            options: [
              { label: 'Urgente', value: 'urgent' },
              { label: 'Alta', value: 'high' },
              { label: 'Media', value: 'medium' },
              { label: 'Baja', value: 'low' },
            ],
          },
          {
            key: 'category',
            label: 'Categoría',
            value: categoryFilter,
            onChange: (v) => {
              setCategoryFilter(v);
              navigateWithParams({ category: v, page: '1' });
            },
            options: [
              { label: 'Facturación / Pagos', value: 'billing' },
              { label: 'Problema técnico', value: 'technical' },
              { label: 'Cuenta / Acceso', value: 'account' },
              { label: 'Solicitud funcionalidad', value: 'feature_request' },
              { label: 'Otro', value: 'other' },
            ],
          },
          {
            key: 'assigned_to',
            label: 'Asignación',
            value: assignedFilter,
            onChange: (v) => {
              setAssignedFilter(v);
              navigateWithParams({ assigned_to: v, page: '1' });
            },
            options: [
              { label: 'Mis tickets', value: 'me' },
              { label: 'Sin asignar', value: 'unassigned' },
            ],
          },
        ]}
        actions={
          <div className="flex gap-2">
            <button
              onClick={handleSearchSubmit}
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
            >
              Buscar
            </button>
            <button
              onClick={() => router.push('/admin/soporte/nuevo')}
              className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
            >
              <Plus className="h-4 w-4" />
              Nuevo ticket
            </button>
          </div>
        }
      />

      {/* Table */}
      <DataTable
        columns={columns}
        data={(initialData?.results ?? []) as (AdminTicketRow & Record<string, unknown>)[]}
        keyExtractor={(row) => row.id}
        loading={false}
        error={initialData === null ? 'No se pudieron cargar los tickets.' : null}
        emptyTitle="Sin tickets"
        emptyDescription="No se encontraron tickets con los filtros seleccionados."
        onRowClick={(row) => router.push(`/admin/soporte/${row.id}`)}
      />

      {/* Pagination */}
      {initialData && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-slate-500">
            {initialData.total} ticket{initialData.total !== 1 ? 's' : ''} en total
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
