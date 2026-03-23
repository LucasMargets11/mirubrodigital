"use client";

import {
  Building2,
  FlaskConical,
  AlertTriangle,
  Users,
  Activity,
  Bell,
} from 'lucide-react';

import { StatCard } from '@/components/admin/stat-card';
import { SectionCard } from '@/components/admin/section-card';
import { EmptyState } from '@/components/admin/empty-state';
import { ErrorState } from '@/components/admin/error-state';
import type { AdminDashboardMetrics } from '@/lib/admin/types';

type DashboardContentProps = {
  metrics: AdminDashboardMetrics | null;
};

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
    LOGIN_FAILED: 'Intento de login fallido',
    EMAIL_VERIFIED: 'Email verificado',
    ONBOARDING_COMPLETED: 'Onboarding completado',
    CASH_SESSION_OPENED: 'Caja abierta',
    CASH_SESSION_CLOSED: 'Caja cerrada',
    SALE_CREATED_POS: 'Venta POS',
    PASSWORD_RESET: 'Contraseña reseteada',
  };
  return actionMap[action] ?? action.replace(/_/g, ' ').toLowerCase();
}

function formatTime(dateStr: string | null): string {
  if (!dateStr) return '—';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);

  if (diffMin < 1) return 'ahora';
  if (diffMin < 60) return `hace ${diffMin}m`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `hace ${diffHours}h`;
  const diffDays = Math.floor(diffHours / 24);
  return `hace ${diffDays}d`;
}

export function DashboardContent({ metrics }: DashboardContentProps) {
  if (!metrics) {
    return (
      <ErrorState
        title="No se pudieron cargar las métricas"
        message="Verificá tu conexión o intentá de nuevo."
      />
    );
  }

  const { kpis, alerts, recent_activity, recent_activity_count_24h } = metrics;

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Clientes activos"
          value={kpis.active_businesses}
          description="Negocios con suscripción activa"
          icon={Building2}
        />
        <StatCard
          title="En prueba"
          value={kpis.trial_businesses}
          description="Negocios en período de trial"
          icon={FlaskConical}
        />
        <StatCard
          title="Pagos con problema"
          value={kpis.past_due_businesses}
          description="Negocios con pago vencido"
          icon={AlertTriangle}
          className={kpis.past_due_businesses > 0 ? 'border-amber-200 bg-amber-50' : undefined}
        />
        <StatCard
          title="Usuarios totales"
          value={kpis.total_users}
          description="Usuarios registrados en la plataforma"
          icon={Users}
        />
      </div>

      {/* Alerts */}
      <SectionCard
        title="Alertas operativas"
        description="Situaciones que requieren atención"
      >
        {alerts.length === 0 ? (
          <p className="text-sm text-slate-500">Sin alertas activas.</p>
        ) : (
          <ul className="space-y-2">
            {alerts.map((alert, idx) => (
              <li
                key={idx}
                className={`flex items-start gap-3 rounded-lg px-4 py-3 text-sm ${
                  alert.type === 'warning'
                    ? 'bg-amber-50 text-amber-800 border border-amber-200'
                    : alert.type === 'error'
                      ? 'bg-red-50 text-red-800 border border-red-200'
                      : 'bg-blue-50 text-blue-800 border border-blue-200'
                }`}
              >
                <Bell className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{alert.message}</span>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      {/* Recent Activity */}
      <SectionCard
        title="Actividad reciente"
        description={`${recent_activity_count_24h} eventos en las últimas 24 horas`}
      >
        {recent_activity.length === 0 ? (
          <EmptyState
            icon={<Activity className="h-8 w-8" />}
            title="Sin actividad reciente"
            description="No se registraron eventos recientemente."
          />
        ) : (
          <div className="divide-y divide-slate-100">
            {recent_activity.map((entry) => (
              <div key={entry.id} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
                <div className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-brand-500" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-slate-800">
                    <span className="font-medium">{formatAction(entry.action)}</span>
                    {entry.business_name && entry.business_name !== '—' && (
                      <span className="text-slate-500"> · {entry.business_name}</span>
                    )}
                  </p>
                  <p className="text-xs text-slate-500">
                    {entry.actor_email} · {formatTime(entry.created_at)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </SectionCard>
    </div>
  );
}
