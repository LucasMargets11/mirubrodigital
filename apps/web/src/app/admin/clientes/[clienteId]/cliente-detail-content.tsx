"use client";

import { useState } from 'react';
import Link from 'next/link';
import {
  Building2,
  Users,
  CreditCard,
  FileText,
  Clock,
  Shield,
  MessageSquare,
  ExternalLink,
  AlertTriangle,
  Send,
  Ticket,
} from 'lucide-react';

import { SectionCard } from '@/components/admin/section-card';
import { StatusBadge } from '@/components/admin/status-badge';
import { QRResenasCard } from '@/components/admin/qr-reviews-card';
import { apiPost } from '@/lib/api/client';
import type { AdminInternalNote } from '@/lib/admin/types';
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
  ticketStatusLabel,
  ticketStatusColor,
  ticketPriorityColor,
} from '@/lib/admin/display';
import type { AdminClientDetail } from '@/lib/admin/types';

type Props = {
  client: AdminClientDetail;
};

export function ClienteDetailContent({ client }: Props) {
  const [noteBody, setNoteBody] = useState('');
  const [noteSubmitting, setNoteSubmitting] = useState(false);
  const [notes, setNotes] = useState(client.notes);

  const handleNoteSubmit = async () => {
    if (!noteBody.trim() || noteSubmitting) return;
    setNoteSubmitting(true);
    try {
      const note = await apiPost<AdminInternalNote>('/api/v1/platform-admin/notes/', {
        target_type: 'business',
        target_id: String(client.id),
        body: noteBody.trim(),
      });
      setNotes((prev) => [note, ...prev]);
      setNoteBody('');
    } catch {
      // apiPost throws on non-2xx — silently ignore for now
    } finally {
      setNoteSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Risk badges */}
      {client.risk_badges.length > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
          <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0" />
          <div className="flex flex-wrap gap-2">
            {client.risk_badges.map((b) => (
              <StatusBadge key={b} label={riskLabel(b)} colorClass={riskColor(b)} />
            ))}
          </div>
        </div>
      )}

      {/* Quick actions */}
      <div className="flex flex-wrap gap-2">
        {client.subscription && (
          <Link
            href={`/admin/suscripciones/${client.subscription.id}`}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <CreditCard className="h-4 w-4" />
            Ver suscripción
            <ExternalLink className="h-3 w-3 text-slate-400" />
          </Link>
        )}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left column: main info */}
        <div className="lg:col-span-2 space-y-6">
          {/* General data */}
          <SectionCard title="Datos generales" description="Información del negocio">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <InfoItem label="Nombre" value={client.name} />
              <InfoItem label="Slug" value={client.slug || '—'} />
              <InfoItem label="Estado">
                <StatusBadge label={statusLabel(client.status)} colorClass={statusColor(client.status)} />
              </InfoItem>
              <InfoItem label="Tipo de servicio" value={client.service_type || '—'} />
              <InfoItem label="País" value={client.country} />
              <InfoItem label="Moneda" value={client.currency} />
              <InfoItem label="Fecha de alta" value={formatDate(client.created_at)} />
              <InfoItem label="Activado" value={formatDate(client.activated_at)} />
              {client.owner && (
                <>
                  <InfoItem label="Owner" value={client.owner.name} />
                  <InfoItem label="Email owner" value={client.owner.email} />
                </>
              )}
            </div>
          </SectionCard>

          {/* Plan and limits */}
          <SectionCard title="Plan y suscripción" description="Suscripción actual vinculada">
            {client.subscription ? (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <InfoItem label="Plan" value={planLabel(client.subscription.plan_code)} />
                <InfoItem label="Estado suscripción">
                  <StatusBadge
                    label={statusLabel(client.subscription.admin_status)}
                    colorClass={statusColor(client.subscription.admin_status)}
                  />
                </InfoItem>
                <InfoItem label="Provider" value={providerLabel(client.subscription.provider)} />
                <InfoItem label="Provider ID" value={client.subscription.provider_sub_id || '—'} />
                <InfoItem label="Inicio período" value={formatDate(client.subscription.current_period_start)} />
                <InfoItem label="Próxima renovación" value={formatDate(client.subscription.current_period_end)} />
                {client.subscription.cancel_at_period_end && (
                  <InfoItem label="Cancelación programada" value={formatDate(client.subscription.cancel_requested_at)} />
                )}
                {client.subscription.canceled_at && (
                  <InfoItem label="Cancelado el" value={formatDate(client.subscription.canceled_at)} />
                )}
                {client.subscription.trial_ends_at && (
                  <InfoItem label="Trial hasta" value={formatDate(client.subscription.trial_ends_at)} />
                )}
              </div>
            ) : (
              <p className="text-sm text-slate-500">Sin suscripción activa.</p>
            )}
          </SectionCard>

          {/* Recent payments */}
          <SectionCard title="Pagos recientes" description="Últimos intentos de cobro">
            {client.recent_payments.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-xs text-slate-500 uppercase">
                      <th className="pb-2 text-left">Fecha</th>
                      <th className="pb-2 text-left">Monto</th>
                      <th className="pb-2 text-left">Estado</th>
                      <th className="pb-2 text-left">Error</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {client.recent_payments.map((p) => (
                      <tr key={p.id}>
                        <td className="py-2 text-slate-600">{formatDateTime(p.attempt_at)}</td>
                        <td className="py-2 font-medium">${p.amount} {p.currency}</td>
                        <td className="py-2">
                          <StatusBadge label={paymentStatusLabel(p.status)} colorClass={paymentStatusColor(p.status)} />
                        </td>
                        <td className="py-2 text-xs text-slate-500">{p.failure_reason || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-slate-500">Sin pagos registrados.</p>
            )}
          </SectionCard>

          {/* Recent events */}
          <SectionCard title="Eventos de billing" description="Últimos eventos del proveedor">
            {client.recent_events.length > 0 ? (
              <div className="space-y-2">
                {client.recent_events.map((ev) => (
                  <div key={ev.id} className="flex items-start justify-between rounded-lg border border-slate-100 px-3 py-2">
                    <div>
                      <p className="text-sm font-medium text-slate-800">{eventTypeLabel(ev.event_type)}</p>
                      <p className="text-xs text-slate-500">{formatDateTime(ev.received_at)}</p>
                    </div>
                    <StatusBadge
                      label={ev.status}
                      colorClass={ev.status === 'error' ? 'bg-red-100 text-red-700' : 'bg-slate-100 text-slate-600'}
                    />
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500">Sin eventos registrados.</p>
            )}
          </SectionCard>

          {/* Audit */}
          <SectionCard title="Actividad reciente" description="Auditoría del negocio">
            {client.recent_audit.length > 0 ? (
              <div className="space-y-2">
                {client.recent_audit.map((a) => (
                  <div key={a.id} className="flex items-start gap-2 py-1.5">
                    <div className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-slate-400" />
                    <div>
                      <p className="text-sm text-slate-700">
                        <span className="font-medium">{a.action.replace(/_/g, ' ').toLowerCase()}</span>
                      </p>
                      <p className="text-xs text-slate-500">{a.actor_email} · {formatRelativeTime(a.created_at)}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500">Sin actividad registrada.</p>
            )}
          </SectionCard>

          {/* QR de Reseñas — only shown for qr_reviews businesses */}
          {client.service_type === 'qr_reviews' && (
            <QRResenasCard businessId={client.id} />
          )}
        </div>

        {/* Right column: sidebar */}
        <div className="space-y-6">
          {/* Members */}
          <SectionCard title="Usuarios" description={`${client.member_count} miembros activos`}>
            <div className="space-y-2">
              {client.members.map((m) => (
                <div key={m.user_id} className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2">
                  <div>
                    <p className="text-sm font-medium text-slate-800">{m.name}</p>
                    <p className="text-xs text-slate-500">{m.email}</p>
                  </div>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">{m.role}</span>
                </div>
              ))}
              {client.member_count > client.members.length && (
                <p className="text-xs text-slate-400 text-center">
                  +{client.member_count - client.members.length} más
                </p>
              )}
            </div>
          </SectionCard>

          {/* Branches */}
          {client.branch_count > 0 && (
            <SectionCard title="Sucursales" description={`${client.branch_count} sucursal(es)`}>
              <p className="text-sm text-slate-600">
                Este negocio tiene {client.branch_count} sucursal(es) bajo su gestión.
              </p>
            </SectionCard>
          )}

          {/* Support summary */}
          <SectionCard
            title="Soporte"
            description={`${client.support_summary.total_tickets} ticket(s) en total`}
          >
            <div className="space-y-3">
              {/* Quick stats */}
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="rounded-lg bg-blue-50 px-2 py-2">
                  <p className="text-lg font-semibold text-blue-700">{client.support_summary.open_tickets}</p>
                  <p className="text-xs text-blue-600">Abiertos</p>
                </div>
                <div className="rounded-lg bg-emerald-50 px-2 py-2">
                  <p className="text-lg font-semibold text-emerald-700">{client.support_summary.resolved_tickets}</p>
                  <p className="text-xs text-emerald-600">Resueltos</p>
                </div>
                <div className="rounded-lg bg-slate-50 px-2 py-2">
                  <p className="text-lg font-semibold text-slate-700">{client.support_summary.total_tickets}</p>
                  <p className="text-xs text-slate-500">Total</p>
                </div>
              </div>

              {/* Last activity */}
              {client.support_summary.last_ticket_reference && (
                <p className="text-xs text-slate-500">
                  Último ticket: <span className="font-medium text-slate-700">{client.support_summary.last_ticket_reference}</span>
                  {client.support_summary.last_ticket_at && (
                    <span suppressHydrationWarning> · {formatRelativeTime(client.support_summary.last_ticket_at)}</span>
                  )}
                </p>
              )}

              {/* Recent tickets */}
              {client.support_summary.recent_tickets.length > 0 ? (
                <div className="space-y-1.5">
                  {client.support_summary.recent_tickets.map((t) => (
                    <Link
                      key={t.id}
                      href={`/admin/soporte/${t.id}`}
                      className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2 hover:bg-slate-50 transition-colors"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-slate-800 truncate">
                          <span className="text-slate-400 mr-1">{t.reference}</span>
                          {t.subject}
                        </p>
                        <p className="text-xs text-slate-500" suppressHydrationWarning>{formatRelativeTime(t.created_at)}</p>
                      </div>
                      <div className="ml-2 flex items-center gap-1.5 shrink-0">
                        <StatusBadge label={ticketStatusLabel(t.status)} colorClass={ticketStatusColor(t.status)} />
                        <span className={`inline-flex rounded-full px-1.5 py-0.5 text-[10px] font-medium ${ticketPriorityColor(t.priority)}`}>
                          {t.priority[0]?.toUpperCase()}
                        </span>
                      </div>
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-400">Sin tickets registrados.</p>
              )}

              {/* View all link */}
              {client.support_summary.total_tickets > 0 && (
                <Link
                  href={`/admin/soporte?business=${client.id}`}
                  className="inline-flex items-center gap-1 text-sm font-medium text-brand-600 hover:text-brand-700"
                >
                  <Ticket className="h-3.5 w-3.5" />
                  Ver todos los tickets
                  <ExternalLink className="h-3 w-3" />
                </Link>
              )}
            </div>
          </SectionCard>

          {/* Billing profile */}
          {client.billing_profile && (
            <SectionCard title="Perfil fiscal">
              <div className="space-y-2 text-sm">
                <InfoItem label="Razón social" value={client.billing_profile.legal_name || '—'} />
                <InfoItem label="CUIT" value={client.billing_profile.tax_id || '—'} />
                <InfoItem label="Cond. IVA" value={client.billing_profile.vat_condition || '—'} />
              </div>
            </SectionCard>
          )}

          {/* Internal Notes */}
          <SectionCard
            title="Notas internas"
            description="Observaciones del staff (no visibles para el cliente)"
          >
            <div className="space-y-3">
              {/* Note input */}
              <div className="space-y-2">
                <textarea
                  value={noteBody}
                  onChange={(e) => setNoteBody(e.target.value)}
                  placeholder="Agregar observación interna..."
                  rows={3}
                  maxLength={2000}
                  className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-500 resize-none"
                />
                <button
                  onClick={handleNoteSubmit}
                  disabled={!noteBody.trim() || noteSubmitting}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Send className="h-3.5 w-3.5" />
                  {noteSubmitting ? 'Guardando...' : 'Agregar nota'}
                </button>
              </div>

              {/* Notes list */}
              {notes.length > 0 ? (
                <div className="divide-y divide-slate-100">
                  {notes.map((note) => (
                    <div key={note.id} className="py-3 first:pt-0">
                      <p className="text-sm text-slate-800 whitespace-pre-wrap">{note.body}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        {note.author_name} · {formatRelativeTime(note.created_at)}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-400">Sin notas internas.</p>
              )}
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}

// ── Helper component ────────────────────────────────────────────────────────

function InfoItem({
  label,
  value,
  children,
}: {
  label: string;
  value?: string;
  children?: React.ReactNode;
}) {
  return (
    <div>
      <dt className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-900">{children ?? value ?? '—'}</dd>
    </div>
  );
}
