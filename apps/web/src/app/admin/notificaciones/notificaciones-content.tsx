"use client";

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Bell, CheckCheck, Archive, CheckCircle2 } from 'lucide-react';

import { DataTable, type DataTableColumn } from '@/components/admin/data-table';
import { FilterBar } from '@/components/admin/filter-bar';
import { Pagination } from '@/components/admin/pagination';
import { StatusBadge } from '@/components/admin/status-badge';
import { EmptyState } from '@/components/admin/empty-state';
import {
  NOTIF_SEVERITY_LABEL,
  NOTIF_SEVERITY_COLOR,
  NOTIF_STATUS_LABEL,
  NOTIF_STATUS_COLOR,
} from '@/components/admin/notification-item';
import {
  markAdminNotificationRead,
  archiveAdminNotification,
  resolveAdminNotification,
} from '@/lib/admin/notifications.client';
import type {
  AdminNotification,
  AdminNotificationList,
  AdminNotificationStatus,
  AdminNotificationSeverity,
  AdminNotificationType,
} from '@/lib/admin/types';

// ── Display helpers ───────────────────────────────────────────────────────

const NOTIF_TYPE_LABEL: Record<AdminNotificationType, string> = {
  support_ticket_created: 'Ticket creado',
  support_ticket_urgent: 'Ticket urgente',
  support_ticket_stale: 'Ticket inactivo',
  support_ticket_reopened: 'Ticket reabierto',
  billing_payment_failure: 'Pago fallido',
  billing_cancel_request: 'Solicitud de baja',
  billing_suspended: 'Suscripción suspendida',
  billing_payment_ok: 'Pago OK',
  review_negative: 'Reseña negativa',
  review_spike: 'Pico de reseñas',
  security_mfa_reset: 'Reset MFA',
  security_role_changed: 'Cambio de rol',
  security_login_failed: 'Login fallido',
  security_staff_changed: 'Staff modificado',
  system_webhook_failed: 'Webhook fallido',
  system_email_failed: 'Email fallido',
};

function formatDateTime(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('es-AR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

// ── Filter options ────────────────────────────────────────────────────────

const STATUS_OPTIONS = [
  { label: 'Todas', value: '' },
  { label: 'No leídas', value: 'unread' },
  { label: 'Leídas', value: 'read' },
  { label: 'Resueltas', value: 'resolved' },
  { label: 'Archivadas', value: 'archived' },
];

const SEVERITY_OPTIONS = [
  { label: 'Todas', value: '' },
  { label: 'Crítico', value: 'critical' },
  { label: 'Advertencia', value: 'warning' },
  { label: 'Info', value: 'info' },
  { label: 'OK', value: 'success' },
];

const TYPE_OPTIONS = [
  { label: 'Todos', value: '' },
  { label: 'Soporte — ticket creado', value: 'support_ticket_created' },
  { label: 'Soporte — urgente', value: 'support_ticket_urgent' },
  { label: 'Soporte — inactivo', value: 'support_ticket_stale' },
  { label: 'Soporte — reabierto', value: 'support_ticket_reopened' },
  { label: 'Billing — pago fallido', value: 'billing_payment_failure' },
  { label: 'Billing — baja solicitada', value: 'billing_cancel_request' },
  { label: 'Billing — suspendida', value: 'billing_suspended' },
  { label: 'Billing — pago OK', value: 'billing_payment_ok' },
  { label: 'Reviews — negativa', value: 'review_negative' },
  { label: 'Reviews — pico', value: 'review_spike' },
  { label: 'Seguridad — MFA reset', value: 'security_mfa_reset' },
  { label: 'Seguridad — rol cambiado', value: 'security_role_changed' },
  { label: 'Seguridad — login fallido', value: 'security_login_failed' },
  { label: 'Seguridad — staff modificado', value: 'security_staff_changed' },
  { label: 'Sistema — webhook fallido', value: 'system_webhook_failed' },
  { label: 'Sistema — email fallido', value: 'system_email_failed' },
];

// ── Props ─────────────────────────────────────────────────────────────────

type Props = {
  initialData: AdminNotificationList | null;
  initialParams: {
    status?: string;
    severity?: string;
    type?: string;
    page?: string;
  };
};

// ── Component ─────────────────────────────────────────────────────────────

export function NotificacionesContent({ initialData, initialParams }: Props) {
  const router = useRouter();

  const [statusFilter, setStatusFilter] = useState(initialParams.status ?? '');
  const [severityFilter, setSeverityFilter] = useState(initialParams.severity ?? '');
  const [typeFilter, setTypeFilter] = useState(initialParams.type ?? '');

  // Local data state for optimistic / action updates
  const [rows, setRows] = useState<AdminNotification[]>(initialData?.results ?? []);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

  const currentPage = initialData?.page ?? 1;
  const totalPages = initialData?.total_pages ?? 1;
  const total = initialData?.total ?? 0;

  // Navigate with current filter state + overrides
  const navigate = useCallback(
    (overrides: Record<string, string>) => {
      const params = new URLSearchParams();
      const merged: Record<string, string> = {
        status: statusFilter,
        severity: severityFilter,
        type: typeFilter,
        ...overrides,
      };
      for (const [k, v] of Object.entries(merged)) {
        if (v) params.set(k, v);
      }
      router.push(`/admin/notificaciones?${params.toString()}`);
    },
    [statusFilter, severityFilter, typeFilter, router],
  );

  const applyFilters = useCallback(() => {
    navigate({ page: '1' });
  }, [navigate]);

  // ── Actions ─────────────────────────────────────────────────────────────

  const updateRow = useCallback((updated: AdminNotification) => {
    setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
  }, []);

  const handleRead = useCallback(
    async (id: string) => {
      setActionError(null);
      setPendingId(id);
      try {
        const updated = await markAdminNotificationRead(id);
        updateRow(updated);
      } catch (e) {
        setActionError(e instanceof Error ? e.message : 'Error al marcar como leída.');
      } finally {
        setPendingId(null);
      }
    },
    [updateRow],
  );

  const handleArchive = useCallback(
    async (id: string) => {
      setActionError(null);
      setPendingId(id);
      try {
        const updated = await archiveAdminNotification(id);
        updateRow(updated);
      } catch (e) {
        setActionError(e instanceof Error ? e.message : 'Error al archivar.');
      } finally {
        setPendingId(null);
      }
    },
    [updateRow],
  );

  const handleResolve = useCallback(
    async (id: string) => {
      setActionError(null);
      setPendingId(id);
      try {
        const updated = await resolveAdminNotification(id);
        updateRow(updated);
      } catch (e) {
        setActionError(e instanceof Error ? e.message : 'Error al resolver.');
      } finally {
        setPendingId(null);
      }
    },
    [updateRow],
  );

  // ── Table columns ─────────────────────────────────────────────────────

  const columns: DataTableColumn<AdminNotification>[] = [
    {
      key: 'severity',
      header: 'Sev.',
      render: (row) => (
        <StatusBadge
          label={NOTIF_SEVERITY_LABEL[row.severity] ?? row.severity}
          colorClass={NOTIF_SEVERITY_COLOR[row.severity] ?? 'bg-slate-100 text-slate-600'}
        />
      ),
      className: 'w-24',
    },
    {
      key: 'status',
      header: 'Estado',
      render: (row) => (
        <StatusBadge
          label={NOTIF_STATUS_LABEL[row.status] ?? row.status}
          colorClass={NOTIF_STATUS_COLOR[row.status] ?? 'bg-slate-100 text-slate-600'}
        />
      ),
      className: 'w-28',
    },
    {
      key: 'title',
      header: 'Notificación',
      render: (row) => (
        <div className="max-w-sm">
          <p className={`font-medium text-sm ${row.status === 'unread' ? 'text-slate-900' : 'text-slate-600'}`}>
            {row.title}
          </p>
          {row.message && (
            <p className="mt-0.5 text-xs text-slate-400 line-clamp-1">{row.message}</p>
          )}
        </div>
      ),
    },
    {
      key: 'notif_type',
      header: 'Tipo',
      render: (row) => (
        <span className="text-xs text-slate-500">{NOTIF_TYPE_LABEL[row.notif_type] ?? row.notif_type}</span>
      ),
    },
    {
      key: 'business_name',
      header: 'Negocio',
      render: (row) =>
        row.business_name ? (
          <span className="text-sm text-slate-700">{row.business_name}</span>
        ) : (
          <span className="text-xs text-slate-400">—</span>
        ),
    },
    {
      key: 'created_at',
      header: 'Fecha',
      render: (row) => (
        <span className="text-xs text-slate-400">{formatDateTime(row.created_at)}</span>
      ),
      className: 'w-36',
    },
    {
      key: 'actions',
      header: 'Acciones',
      render: (row) => {
        const busy = pendingId === row.id;
        return (
          <div className="flex items-center gap-1">
            {row.status === 'unread' && (
              <button
                type="button"
                disabled={busy}
                onClick={(e) => { e.stopPropagation(); handleRead(row.id); }}
                className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-40 transition-colors"
                title="Marcar como leída"
                aria-label="Marcar como leída"
              >
                <CheckCheck className="h-4 w-4" />
              </button>
            )}
            {row.status !== 'archived' && (
              <button
                type="button"
                disabled={busy}
                onClick={(e) => { e.stopPropagation(); handleArchive(row.id); }}
                className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-40 transition-colors"
                title="Archivar"
                aria-label="Archivar"
              >
                <Archive className="h-4 w-4" />
              </button>
            )}
            {row.status !== 'resolved' && row.status !== 'archived' && (
              <button
                type="button"
                disabled={busy}
                onClick={(e) => { e.stopPropagation(); handleResolve(row.id); }}
                className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-40 transition-colors"
                title="Resolver"
                aria-label="Resolver"
              >
                <CheckCircle2 className="h-4 w-4" />
              </button>
            )}
          </div>
        );
      },
      className: 'w-28',
    },
  ];

  return (
    <div className="space-y-4">
      {/* Action error feedback */}
      {actionError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {actionError}
          <button
            type="button"
            onClick={() => setActionError(null)}
            className="ml-2 text-red-500 hover:underline text-xs"
          >
            Cerrar
          </button>
        </div>
      )}

      {/* Filters */}
      <FilterBar
        filters={[
          {
            key: 'status',
            label: 'Estado',
            options: STATUS_OPTIONS,
            value: statusFilter,
            onChange: (v) => { setStatusFilter(v); navigate({ status: v, page: '1' }); },
          },
          {
            key: 'severity',
            label: 'Severidad',
            options: SEVERITY_OPTIONS,
            value: severityFilter,
            onChange: (v) => { setSeverityFilter(v); navigate({ severity: v, page: '1' }); },
          },
          {
            key: 'type',
            label: 'Tipo',
            options: TYPE_OPTIONS,
            value: typeFilter,
            onChange: (v) => { setTypeFilter(v); navigate({ type: v, page: '1' }); },
          },
        ]}
      />

      {/* Summary row */}
      {total > 0 && (
        <p className="text-sm text-slate-500">
          {total} notificación{total !== 1 ? 'es' : ''}
          {initialData?.unread_count ? ` · ${initialData.unread_count} sin leer` : ''}
        </p>
      )}

      {/* Table */}
      {rows.length === 0 ? (
        <EmptyState
          icon={<Bell className="h-10 w-10" />}
          title="Sin notificaciones"
          description="No hay notificaciones con los filtros aplicados."
        />
      ) : (
        <DataTable<AdminNotification>
          columns={columns}
          data={rows}
          keyExtractor={(row) => row.id}
          emptyTitle="Sin notificaciones"
          emptyDescription="No hay notificaciones con los filtros aplicados."
        />
      )}

      {/* Pagination */}
      <Pagination
        page={currentPage}
        totalPages={totalPages}
        onPageChange={(p) => navigate({ page: String(p) })}
      />
    </div>
  );
}
