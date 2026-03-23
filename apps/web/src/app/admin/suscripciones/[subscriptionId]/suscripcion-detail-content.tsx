"use client";

import { useState } from 'react';
import Link from 'next/link';
import {
  Building2,
  CreditCard,
  FileText,
  Clock,
  AlertTriangle,
  Send,
  ExternalLink,
  RefreshCw,
  MessageSquare,
  Globe,
} from 'lucide-react';

import { SectionCard } from '@/components/admin/section-card';
import { StatusBadge } from '@/components/admin/status-badge';
import {
  statusLabel,
  statusColor,
  riskLabel,
  riskColor,
  planLabel,
  providerLabel,
  paymentStatusLabel,
  paymentStatusColor,
  eventTypeLabel,
  formatDate,
  formatDateTime,
  formatRelativeTime,
} from '@/lib/admin/display';
import type { AdminSubscriptionDetail } from '@/lib/admin/types';

type Props = {
  subscription: AdminSubscriptionDetail;
};

export function SuscripcionDetailContent({ subscription }: Props) {
  const [noteBody, setNoteBody] = useState('');
  const [noteSubmitting, setNoteSubmitting] = useState(false);
  const [notes, setNotes] = useState(subscription.notes);

  const handleNoteSubmit = async () => {
    if (!noteBody.trim() || noteSubmitting) return;
    setNoteSubmitting(true);
    try {
      const res = await fetch('/api/v1/platform-admin/notes/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          target_type: 'subscription_v2',
          target_id: subscription.id,
          body: noteBody.trim(),
        }),
      });
      if (res.ok) {
        const note = await res.json();
        setNotes((prev) => [note, ...prev]);
        setNoteBody('');
      }
    } finally {
      setNoteSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Risk badges */}
      {subscription.risk_badges.length > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
          <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0" />
          <div className="flex flex-wrap gap-2">
            {subscription.risk_badges.map((b) => (
              <StatusBadge key={b} label={riskLabel(b)} colorClass={riskColor(b)} />
            ))}
          </div>
        </div>
      )}

      {/* Quick actions */}
      <div className="flex flex-wrap gap-2">
        {subscription.business && (
          <Link
            href={`/admin/clientes/${subscription.business.id}`}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <Building2 className="h-4 w-4" />
            Ver cliente: {subscription.business.name}
            <ExternalLink className="h-3 w-3 text-slate-400" />
          </Link>
        )}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left column: main info */}
        <div className="lg:col-span-2 space-y-6">
          {/* General data */}
          <SectionCard title="Datos de la suscripción">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm">
              <div>
                <dt className="text-slate-500">ID</dt>
                <dd className="mt-0.5 font-mono text-xs text-slate-700">{subscription.id}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Plan</dt>
                <dd className="mt-0.5 font-medium">{planLabel(subscription.plan_code)}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Estado</dt>
                <dd className="mt-1">
                  <StatusBadge
                    label={statusLabel(subscription.admin_status)}
                    colorClass={statusColor(subscription.admin_status)}
                  />
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Provider</dt>
                <dd className="mt-0.5">{providerLabel(subscription.provider)}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Provider Sub ID</dt>
                <dd className="mt-0.5 font-mono text-xs text-slate-600">
                  {subscription.provider_sub_id || '—'}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Ref. externa</dt>
                <dd className="mt-0.5 font-mono text-xs text-slate-600">
                  {subscription.external_reference || '—'}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Servicio</dt>
                <dd className="mt-0.5">{subscription.service_type || '—'}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Creada</dt>
                <dd className="mt-0.5">{formatDateTime(subscription.created_at)}</dd>
              </div>
            </dl>
          </SectionCard>

          {/* Period & trial */}
          <SectionCard title="Período y prueba">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm">
              <div>
                <dt className="text-slate-500">Período actual</dt>
                <dd className="mt-0.5">
                  {formatDate(subscription.current_period_start)} – {formatDate(subscription.current_period_end)}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Trial</dt>
                <dd className="mt-0.5">
                  {subscription.trial_starts_at
                    ? `${formatDate(subscription.trial_starts_at)} – ${formatDate(subscription.trial_ends_at)}`
                    : '—'}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Gracia hasta</dt>
                <dd className="mt-0.5">{formatDate(subscription.grace_until)}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Reintentos</dt>
                <dd className={`mt-0.5 font-medium ${subscription.retry_count > 0 ? 'text-amber-600' : ''}`}>
                  {subscription.retry_count}
                </dd>
              </div>
            </dl>
          </SectionCard>

          {/* Cancellation */}
          {(subscription.cancel_at_period_end || subscription.canceled_at) && (
            <SectionCard title="Cancelación">
              <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm">
                <div>
                  <dt className="text-slate-500">Cancelar al final del período</dt>
                  <dd className="mt-0.5 font-medium">
                    {subscription.cancel_at_period_end ? 'Sí' : 'No'}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Solicitud de cancelación</dt>
                  <dd className="mt-0.5">{formatDateTime(subscription.cancel_requested_at)}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Cancelada en</dt>
                  <dd className="mt-0.5">{formatDateTime(subscription.canceled_at)}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Motivo</dt>
                  <dd className="mt-0.5">{subscription.cancel_reason || '—'}</dd>
                </div>
              </dl>
            </SectionCard>
          )}

          {/* Payments */}
          <SectionCard title="Pagos recientes" description={`${subscription.payments.length} pagos`}>
            {subscription.payments.length === 0 ? (
              <p className="text-sm text-slate-400">No hay pagos registrados.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-left">
                      <th className="pb-2 font-medium text-slate-500">Monto</th>
                      <th className="pb-2 font-medium text-slate-500">Estado</th>
                      <th className="pb-2 font-medium text-slate-500">Fecha</th>
                      <th className="pb-2 font-medium text-slate-500">Motivo rechazo</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {subscription.payments.map((p) => (
                      <tr key={p.id}>
                        <td className="py-2 font-medium">
                          {p.currency} {p.amount}
                        </td>
                        <td className="py-2">
                          <StatusBadge
                            label={paymentStatusLabel(p.status)}
                            colorClass={paymentStatusColor(p.status)}
                          />
                        </td>
                        <td className="py-2 text-slate-600">{formatDateTime(p.attempt_at)}</td>
                        <td className="py-2 text-xs text-slate-500">{p.failure_reason || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </SectionCard>

          {/* Billing Events */}
          <SectionCard title="Eventos de billing" description={`${subscription.events.length} eventos`}>
            {subscription.events.length === 0 ? (
              <p className="text-sm text-slate-400">No hay eventos de billing.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-left">
                      <th className="pb-2 font-medium text-slate-500">Tipo</th>
                      <th className="pb-2 font-medium text-slate-500">Estado</th>
                      <th className="pb-2 font-medium text-slate-500">Recibido</th>
                      <th className="pb-2 font-medium text-slate-500">Error</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {subscription.events.map((e) => (
                      <tr key={e.id}>
                        <td className="py-2 font-medium">{eventTypeLabel(e.event_type)}</td>
                        <td className="py-2">
                          <StatusBadge
                            label={e.status}
                            colorClass={
                              e.status === 'processed'
                                ? 'bg-emerald-100 text-emerald-700'
                                : e.status === 'error'
                                  ? 'bg-red-100 text-red-700'
                                  : 'bg-slate-100 text-slate-500'
                            }
                          />
                        </td>
                        <td className="py-2 text-slate-600">{formatDateTime(e.received_at)}</td>
                        <td className="py-2 text-xs text-red-500">{e.error_message || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </SectionCard>

          {/* Invoice Events */}
          {subscription.invoice_events.length > 0 && (
            <SectionCard
              title="Eventos de facturación"
              description={`${subscription.invoice_events.length} registros`}
            >
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-left">
                      <th className="pb-2 font-medium text-slate-500">Monto</th>
                      <th className="pb-2 font-medium text-slate-500">Estado provider</th>
                      <th className="pb-2 font-medium text-slate-500">Pagado</th>
                      <th className="pb-2 font-medium text-slate-500">Creado</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {subscription.invoice_events.map((inv) => (
                      <tr key={inv.id}>
                        <td className="py-2 font-medium">
                          {inv.currency} {inv.amount}
                        </td>
                        <td className="py-2">
                          <StatusBadge
                            label={inv.provider_status}
                            colorClass={
                              inv.provider_status === 'approved'
                                ? 'bg-emerald-100 text-emerald-700'
                                : 'bg-slate-100 text-slate-500'
                            }
                          />
                        </td>
                        <td className="py-2 text-slate-600">{formatDateTime(inv.paid_at)}</td>
                        <td className="py-2 text-slate-600">{formatDateTime(inv.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </SectionCard>
          )}
        </div>

        {/* Right column */}
        <div className="space-y-6">
          {/* Business link card */}
          {subscription.business && (
            <SectionCard title="Cliente vinculado">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50">
                  <Building2 className="h-5 w-5 text-brand-600" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-slate-900">{subscription.business.name}</p>
                  <p className="text-xs text-slate-500">
                    {subscription.business.slug} · <StatusBadge
                      label={statusLabel(subscription.business.status)}
                      colorClass={statusColor(subscription.business.status)}
                    />
                  </p>
                </div>
                <Link
                  href={`/admin/clientes/${subscription.business.id}`}
                  className="shrink-0 text-brand-600 hover:text-brand-700"
                >
                  <ExternalLink className="h-4 w-4" />
                </Link>
              </div>
            </SectionCard>
          )}

          {/* Price snapshot */}
          {subscription.price_snapshot && (
            <SectionCard title="Snapshot de precios">
              <pre className="overflow-x-auto rounded bg-slate-50 p-3 text-xs text-slate-700">
                {JSON.stringify(subscription.price_snapshot, null, 2)}
              </pre>
            </SectionCard>
          )}

          {/* Webhook errors */}
          {subscription.webhook_errors.length > 0 && (
            <SectionCard
              title="Errores de webhooks"
              description={`${subscription.webhook_errors.length} errores`}
            >
              <div className="space-y-3">
                {subscription.webhook_errors.map((wh) => (
                  <div
                    key={wh.id}
                    className="rounded-lg border border-red-100 bg-red-50 p-3 text-xs"
                  >
                    <div className="flex items-center gap-2 text-red-700">
                      <Globe className="h-3.5 w-3.5" />
                      <span className="font-medium">{wh.topic}.{wh.action}</span>
                    </div>
                    <p className="mt-1 text-red-600">{wh.error_message || '—'}</p>
                    <p className="mt-1 text-slate-500">{formatRelativeTime(wh.received_at)}</p>
                  </div>
                ))}
              </div>
            </SectionCard>
          )}

          {/* Internal notes */}
          <SectionCard
            title="Notas internas"
            description={`${notes.length} nota${notes.length !== 1 ? 's' : ''}`}
          >
            <div className="space-y-4">
              {/* Create note form */}
              <div className="space-y-2">
                <textarea
                  value={noteBody}
                  onChange={(e) => setNoteBody(e.target.value)}
                  placeholder="Escribe una nota interna..."
                  maxLength={2000}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                  rows={3}
                />
                <div className="flex justify-end">
                  <button
                    onClick={handleNoteSubmit}
                    disabled={!noteBody.trim() || noteSubmitting}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
                  >
                    <Send className="h-3.5 w-3.5" />
                    {noteSubmitting ? 'Enviando...' : 'Agregar nota'}
                  </button>
                </div>
              </div>

              {/* Notes list */}
              {notes.length === 0 ? (
                <p className="text-sm text-slate-400">Sin notas aún.</p>
              ) : (
                <div className="space-y-3">
                  {notes.map((note) => (
                    <div key={note.id} className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-slate-700">
                          {note.author_name || note.author_email}
                        </span>
                        <span className="text-xs text-slate-400">
                          {formatRelativeTime(note.created_at)}
                        </span>
                      </div>
                      <p className="mt-1 text-sm text-slate-600 whitespace-pre-wrap">{note.body}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </SectionCard>

          {/* Last updated */}
          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <RefreshCw className="h-3 w-3" />
            Actualizado: {formatDateTime(subscription.updated_at)}
          </div>
        </div>
      </div>
    </div>
  );
}
