'use client';

import {
  Building2,
  CreditCard,
  TicketCheck,
  Users,
  AlertTriangle,
  ShieldAlert,
  Activity,
  BarChart3,
  Bell,
  TrendingUp,
  ArrowRight,
} from 'lucide-react';
import Link from 'next/link';

import { StatCard } from '@/components/admin/stat-card';
import { SectionCard } from '@/components/admin/section-card';
import { ErrorState } from '@/components/admin/error-state';
import { HorizontalRankChart } from '@/lib/charts';
import {
  statusLabel,
  statusColor,
  planLabel,
  providerLabel,
  ticketCategoryLabel,
  formatRelativeTime,
} from '@/lib/admin/display';
import type {
  AdminReportingOverview,
  AdminOperationalAlert,
  AdminActivityEntry,
  AdminDistributionItem,
} from '@/lib/admin/types';

type ReportesContentProps = {
  data: AdminReportingOverview | null;
};

// ── Helpers ─────────────────────────────────────────────────────────────────

function formatAction(action: string): string {
  const actionMap: Record<string, string> = {
    MEMBERSHIP_CREATED: 'Miembro creado',
    MEMBERSHIP_UPDATED: 'Miembro actualizado',
    SUBSCRIPTION_CREATED: 'Suscripción creada',
    SUBSCRIPTION_STATUS_CHANGED: 'Estado de suscripción cambiado',
    SUBSCRIPTION_CANCELED: 'Suscripción cancelada',
    TRIAL_STARTED: 'Prueba iniciada',
    TRIAL_EXPIRED: 'Prueba expirada',
    USER_CREATED: 'Usuario creado',
    LOGIN_FAILED: 'Login fallido',
    EMAIL_VERIFIED: 'Email verificado',
    ONBOARDING_COMPLETED: 'Onboarding completado',
    CASH_SESSION_OPENED: 'Caja abierta',
    CASH_SESSION_CLOSED: 'Caja cerrada',
    SALE_CREATED_POS: 'Venta POS',
    PASSWORD_RESET: 'Contraseña reseteada',
    ADMIN_CLIENT_VIEWED: 'Cliente consultado',
    ADMIN_SUBSCRIPTION_VIEWED: 'Suscripción consultada',
    ADMIN_TICKET_CREATED: 'Ticket creado',
    ADMIN_TICKET_UPDATED: 'Ticket actualizado',
    ADMIN_TICKET_VIEWED: 'Ticket consultado',
    ADMIN_TICKET_MESSAGE: 'Mensaje en ticket',
    ADMIN_NOTE_CREATED: 'Nota creada',
    ADMIN_REPORT_VIEWED: 'Reporte consultado',
    ADMIN_ALERTS_VIEWED: 'Alertas consultadas',
  };
  return actionMap[action] ?? action.replace(/_/g, ' ').toLowerCase();
}

function formatCurrency(value: string): string {
  const num = parseFloat(value);
  if (isNaN(num)) return '$0';
  return new Intl.NumberFormat('es-AR', {
    style: 'currency',
    currency: 'ARS',
    maximumFractionDigits: 0,
  }).format(num);
}

function serviceTypeLabel(st: string | undefined): string {
  if (!st) return '—';
  const map: Record<string, string> = {
    gestion: 'Gestión Comercial',
    restaurante: 'Restaurantes',
    menu_qr: 'Menú QR',
    menu_qr_visual: 'Menú QR Visual',
    menu_qr_marca: 'Menú QR Marca',
  };
  return map[st] ?? st;
}

// ── Distribution Bar ────────────────────────────────────────────────────────

function DistributionBar({
  items,
  labelFn,
  keyField,
}: {
  items: AdminDistributionItem[];
  labelFn: (value: string) => string;
  keyField: string;
}) {
  const total = items.reduce((sum, it) => sum + it.count, 0);
  if (total === 0) {
    return <p className="text-sm text-slate-400">Sin datos.</p>;
  }

  const chartItems = items.map((item) => ({
    name: labelFn((item as Record<string, unknown>)[keyField] as string),
    value: item.count,
  }));

  return (
    <HorizontalRankChart
      items={chartItems}
      formatLabel={(v) => String(v)}
      formatTooltip={(name, value) => {
        const pct = total > 0 ? Math.round((value / total) * 100) : 0;
        return `<div style="font-weight:600;margin-bottom:4px">${name}</div>
          <div style="font-family:ui-monospace,monospace;font-weight:600">${value} <span style="opacity:.6">(${pct}%)</span></div>`;
      }}
    />
  );
}

// ── Alert Row ───────────────────────────────────────────────────────────────

function AlertRow({ alert }: { alert: AdminOperationalAlert }) {
  const isCritical = alert.severity === 'critical';
  return (
    <Link
      href={alert.link as never}
      className={`flex items-start gap-3 rounded-lg px-4 py-3 text-sm transition-colors ${
        isCritical
          ? 'border border-red-200 bg-red-50 text-red-800 hover:bg-red-100'
          : 'border border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100'
      }`}
    >
      {isCritical ? (
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
      ) : (
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      )}
      <div className="flex-1 min-w-0">
        <p className="font-medium">{alert.title}</p>
        <p className="mt-0.5 text-xs opacity-80">{alert.description}</p>
      </div>
      <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 opacity-50" />
    </Link>
  );
}

// ── Activity Entry ──────────────────────────────────────────────────────────

function ActivityRow({ entry }: { entry: AdminActivityEntry }) {
  return (
    <div className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
      <div className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand-500" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-slate-800">
          <span className="font-medium">{formatAction(entry.action)}</span>
          {entry.business_name && entry.business_name !== '—' && (
            <span className="text-slate-500"> · {entry.business_name}</span>
          )}
        </p>
        <p className="text-xs text-slate-500">
          {entry.actor_email} · {formatRelativeTime(entry.created_at)}
        </p>
      </div>
    </div>
  );
}

// ── Main Component ──────────────────────────────────────────────────────────

export function ReportesContent({ data }: ReportesContentProps) {
  if (!data) {
    return (
      <ErrorState
        title="No se pudieron cargar los reportes"
        message="Verificá tu conexión o intentá de nuevo."
      />
    );
  }

  const { kpis, distributions, alerts, recent_activity } = data;
  const criticalCount = alerts.filter((a) => a.severity === 'critical').length;

  return (
    <div className="space-y-6">
      {/* ── KPIs ── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5">
        <StatCard
          title="Clientes activos"
          value={kpis.clients.active}
          description={`${kpis.clients.total} total · ${kpis.clients.trialing} en prueba`}
          icon={Building2}
        />
        <StatCard
          title="Suscripciones activas"
          value={kpis.subscriptions.active}
          description={`${kpis.subscriptions.total} total · ${kpis.subscriptions.scheduled_cancel} cancel. prog.`}
          icon={CreditCard}
        />
        <StatCard
          title="Tickets abiertos"
          value={kpis.tickets.open}
          description={`${kpis.tickets.unassigned} sin asignar`}
          icon={TicketCheck}
          className={kpis.tickets.unassigned > 0 ? 'border-amber-200 bg-amber-50' : undefined}
        />
        <StatCard
          title="Pagos aprobados (30d)"
          value={kpis.payments_30d.approved}
          description={`${formatCurrency(kpis.payments_30d.revenue)} recaudado`}
          icon={TrendingUp}
        />
        <StatCard
          title="Usuarios registrados"
          value={kpis.total_users}
          description="Usuarios activos en la plataforma"
          icon={Users}
        />
      </div>

      {/* ── Status Summary ── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <SectionCard title="Estado de clientes" description="Distribución por estado">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {(['active', 'trialing', 'past_due', 'suspended', 'canceled', 'onboarding'] as const).map(
              (status) => (
                <div key={status} className="text-center">
                  <span
                    className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor(status)}`}
                  >
                    {statusLabel(status)}
                  </span>
                  <p className="mt-1 text-lg font-semibold text-slate-900">
                    {kpis.clients[status]}
                  </p>
                </div>
              ),
            )}
          </div>
        </SectionCard>

        <SectionCard title="Estado de suscripciones" description="Distribución por estado">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {(['active', 'trialing', 'past_due', 'suspended', 'canceled', 'checkout_pending'] as const).map(
              (status) => (
                <div key={status} className="text-center">
                  <span
                    className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor(status)}`}
                  >
                    {statusLabel(status)}
                  </span>
                  <p className="mt-1 text-lg font-semibold text-slate-900">
                    {kpis.subscriptions[status]}
                  </p>
                </div>
              ),
            )}
          </div>
        </SectionCard>
      </div>

      {/* ── Payment Summary ── */}
      <SectionCard title="Pagos — Últimos 30 días" description="Resumen de intentos de pago">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          <div className="text-center">
            <p className="text-2xl font-bold text-emerald-600">{kpis.payments_30d.approved}</p>
            <p className="text-xs text-slate-500">Aprobados</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-red-600">{kpis.payments_30d.rejected}</p>
            <p className="text-xs text-slate-500">Rechazados</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-rose-600">{kpis.payments_30d.chargeback}</p>
            <p className="text-xs text-slate-500">Contracargos</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-violet-600">{kpis.payments_30d.refunded}</p>
            <p className="text-xs text-slate-500">Reembolsos</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-slate-700">
              {formatCurrency(kpis.payments_30d.revenue)}
            </p>
            <p className="text-xs text-slate-500">Recaudado</p>
          </div>
        </div>
      </SectionCard>

      {/* ── Distributions ── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <SectionCard title="Distribución por plan" description="Suscripciones activas/trial/past_due">
          <DistributionBar
            items={distributions.plan_distribution}
            labelFn={planLabel}
            keyField="plan_code"
          />
        </SectionCard>

        <SectionCard title="Distribución por tipo de servicio" description="Clientes activos por vertical">
          <DistributionBar
            items={distributions.service_type_distribution}
            labelFn={serviceTypeLabel}
            keyField="service_type"
          />
        </SectionCard>

        <SectionCard title="Tickets por categoría" description="Tickets abiertos/en curso">
          <DistributionBar
            items={distributions.ticket_category_distribution}
            labelFn={ticketCategoryLabel}
            keyField="category"
          />
        </SectionCard>

        <SectionCard title="Proveedor de pago" description="Suscripciones activas por proveedor">
          <DistributionBar
            items={distributions.provider_distribution}
            labelFn={providerLabel}
            keyField="provider"
          />
        </SectionCard>
      </div>

      {/* ── Operational Alerts ── */}
      <SectionCard
        title="Alertas operativas"
        description={
          criticalCount > 0
            ? `${criticalCount} alerta(s) crítica(s) · ${alerts.length} total`
            : `${alerts.length} alerta(s) activa(s)`
        }
        actions={
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
              criticalCount > 0
                ? 'bg-red-100 text-red-700'
                : alerts.length > 0
                  ? 'bg-amber-100 text-amber-700'
                  : 'bg-emerald-100 text-emerald-700'
            }`}
          >
            <Bell className="h-3 w-3" />
            {criticalCount > 0 ? 'Atención requerida' : alerts.length > 0 ? 'Revisar' : 'Todo OK'}
          </span>
        }
      >
        {alerts.length === 0 ? (
          <p className="text-sm text-slate-500">Sin alertas operativas activas.</p>
        ) : (
          <ul className="space-y-2">
            {alerts.map((alert, idx) => (
              <li key={idx}>
                <AlertRow alert={alert} />
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      {/* ── Recent Activity ── */}
      <SectionCard
        title="Actividad reciente"
        description="Últimas 15 acciones en la plataforma"
        actions={
          <Link
            href="/admin/dashboard"
            className="text-xs text-brand-600 hover:text-brand-700 font-medium"
          >
            Ver dashboard
          </Link>
        }
      >
        {recent_activity.length === 0 ? (
          <p className="text-sm text-slate-400">Sin actividad reciente.</p>
        ) : (
          <div className="divide-y divide-slate-100">
            {recent_activity.map((entry) => (
              <ActivityRow key={entry.id} entry={entry} />
            ))}
          </div>
        )}
      </SectionCard>
    </div>
  );
}
