"use client";

import { useCallback, useRef, useState } from 'react';
import Link from 'next/link';
import {
  Building2,
  CreditCard,
  ExternalLink,
  MessageSquare,
  Send,
  AlertTriangle,
  Clock,
  User,
  Tag,
} from 'lucide-react';

import { SectionCard } from '@/components/admin/section-card';
import { StatusBadge } from '@/components/admin/status-badge';
import { apiPost, apiPatch, ApiError } from '@/lib/api/client';
import {
  ticketStatusLabel,
  ticketStatusColor,
  ticketPriorityLabel,
  ticketPriorityColor,
  ticketCategoryLabel,
  paymentStatusLabel,
  paymentStatusColor,
  eventTypeLabel,
  planLabel,
  statusLabel,
  statusColor,
  formatDate,
  formatDateTime,
  formatRelativeTime,
} from '@/lib/admin/display';
import type {
  AdminTicketDetail,
  AdminTicketMessage,
  AdminStaffMember,
} from '@/lib/admin/types';

type Props = {
  ticket: AdminTicketDetail;
  staffMembers: { results: AdminStaffMember[] } | null;
};

export function TicketDetailContent({ ticket, staffMembers }: Props) {
  const [status, setStatus] = useState(ticket.status);
  const [priority, setPriority] = useState(ticket.priority);
  const [category, setCategory] = useState(ticket.category);
  const [assignedTo, setAssignedTo] = useState(ticket.assigned_to?.id?.toString() ?? '');
  const [messages, setMessages] = useState<AdminTicketMessage[]>(ticket.messages);
  const [messageBody, setMessageBody] = useState('');
  const [updating, setUpdating] = useState(false);
  const [sending, setSending] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const staff = staffMembers?.results ?? [];

  const patchTicket = useCallback(
    async (payload: Record<string, string>, rollback?: () => void) => {
      setUpdating(true);
      setUpdateError(null);
      try {
        const data = await apiPatch<{
          status?: string;
          priority?: string;
          category?: string;
          assigned_to_id?: number | null;
          messages?: AdminTicketMessage[];
        }>(`/api/v1/platform-admin/tickets/${ticket.id}/update/`, payload);
        if (data.status) setStatus(data.status);
        if (data.priority) setPriority(data.priority);
        if (data.category) setCategory(data.category);
        if (data.messages) {
          setMessages(data.messages);
        }
      } catch (err) {
        rollback?.();
        if (err instanceof ApiError) {
          setUpdateError((err.payload as { detail?: string })?.detail ?? 'Error al actualizar el ticket.');
        } else {
          setUpdateError('Error inesperado al actualizar.');
        }
      } finally {
        setUpdating(false);
      }
    },
    [ticket.id],
  );

  const handleSendMessage = useCallback(async () => {
    if (!messageBody.trim() || sending) return;
    setSending(true);
    setSendError(null);
    try {
      const msg = await apiPost<AdminTicketMessage>(
        `/api/v1/platform-admin/tickets/${ticket.id}/messages/`,
        { body: messageBody.trim() },
      );
      setMessages((prev) => [...prev, msg]);
      setMessageBody('');
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    } catch (err) {
      if (err instanceof ApiError) {
        setSendError((err.payload as { detail?: string })?.detail ?? 'Error al enviar el mensaje.');
      } else {
        setSendError('Error inesperado al enviar.');
      }
    } finally {
      setSending(false);
    }
  }, [ticket.id, messageBody, sending]);

  return (
    <div className="space-y-6">
      {/* Quick links */}
      <div className="flex flex-wrap gap-2">
        {ticket.business && (
          <Link
            href={`/admin/clientes/${ticket.business.id}`}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <Building2 className="h-4 w-4" />
            {ticket.business.name}
            <ExternalLink className="h-3 w-3 text-slate-400" />
          </Link>
        )}
        {ticket.subscription && (
          <Link
            href={`/admin/suscripciones/${ticket.subscription.id}`}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <CreditCard className="h-4 w-4" />
            Suscripción ({planLabel(ticket.subscription.plan_code)})
            <ExternalLink className="h-3 w-3 text-slate-400" />
          </Link>
        )}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left column: messages + cross-linked data */}
        <div className="lg:col-span-2 space-y-6">
          {/* Messages thread */}
          <SectionCard title="Conversación" description={`${messages.length} mensaje(s)`}>
            <div className="space-y-4 max-h-[600px] overflow-y-auto pr-1">
              {messages.length > 0 ? (
                messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={
                      msg.is_system
                        ? 'rounded-lg bg-slate-50 px-3 py-2 text-center text-xs text-slate-500 italic'
                        : 'rounded-lg border border-slate-100 px-4 py-3'
                    }
                  >
                    {msg.is_system ? (
                      <span>{msg.body}</span>
                    ) : (
                      <>
                        <div className="flex items-center justify-between">
                          <p className="text-sm font-medium text-slate-800">{msg.author_name}</p>
                          <p className="text-xs text-slate-400" suppressHydrationWarning>{formatRelativeTime(msg.created_at)}</p>
                        </div>
                        <p className="mt-1 text-sm text-slate-700 whitespace-pre-wrap">{msg.body}</p>
                      </>
                    )}
                  </div>
                ))
              ) : (
                <p className="text-sm text-slate-400 text-center py-4">Sin mensajes aún.</p>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Reply box */}
            <div className="mt-4 space-y-2 border-t border-slate-100 pt-4">
              {sendError && (
                <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {sendError}
                </p>
              )}
              <textarea
                value={messageBody}
                onChange={(e) => setMessageBody(e.target.value)}
                placeholder="Escribir respuesta..."
                rows={3}
                maxLength={5000}
                disabled={sending}
                className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-500 resize-none disabled:opacity-50"
              />
              <button
                onClick={handleSendMessage}
                disabled={!messageBody.trim() || sending}
                className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Send className="h-3.5 w-3.5" />
                {sending ? 'Enviando...' : 'Enviar mensaje'}
              </button>
            </div>
          </SectionCard>

          {/* Recent payments */}
          <SectionCard title="Pagos recientes" description="Últimos intentos de cobro del cliente">
            {ticket.recent_payments.length > 0 ? (
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
                    {ticket.recent_payments.map((p) => (
                      <tr key={p.id}>
                        <td className="py-2 text-slate-600" suppressHydrationWarning>{formatDateTime(p.attempt_at)}</td>
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
              <p className="text-sm text-slate-500">Sin pagos registrados para este cliente.</p>
            )}
          </SectionCard>

          {/* Billing events */}
          <SectionCard title="Eventos de billing" description="Últimos eventos del proveedor">
            {ticket.recent_billing_events.length > 0 ? (
              <div className="space-y-2">
                {ticket.recent_billing_events.map((ev) => (
                  <div key={ev.id} className="flex items-start justify-between rounded-lg border border-slate-100 px-3 py-2">
                    <div>
                      <p className="text-sm font-medium text-slate-800">{eventTypeLabel(ev.event_type)}</p>
                      <p className="text-xs text-slate-500" suppressHydrationWarning>{formatDateTime(ev.received_at)}</p>
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
        </div>

        {/* Right column: ticket metadata + actions */}
        <div className="space-y-6">
          {/* Ticket details */}
          <SectionCard title="Detalle del ticket">
            <div className="space-y-4">
              {updateError && (
                <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {updateError}
                </p>
              )}
              <InfoItem label="Estado">
                <select
                  value={status}
                  onChange={(e) => {
                    const prev = status;
                    setStatus(e.target.value);
                    patchTicket({ status: e.target.value }, () => setStatus(prev));
                  }}
                  disabled={updating}
                  className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-sm"
                >
                  <option value="open">Abierto</option>
                  <option value="in_progress">En curso</option>
                  <option value="waiting_on_client">Esperando cliente</option>
                  <option value="resolved">Resuelto</option>
                  <option value="closed">Cerrado</option>
                </select>
              </InfoItem>

              <InfoItem label="Prioridad">
                <select
                  value={priority}
                  onChange={(e) => {
                    const prev = priority;
                    setPriority(e.target.value);
                    patchTicket({ priority: e.target.value }, () => setPriority(prev));
                  }}
                  disabled={updating}
                  className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-sm"
                >
                  <option value="low">Baja</option>
                  <option value="medium">Media</option>
                  <option value="high">Alta</option>
                  <option value="urgent">Urgente</option>
                </select>
              </InfoItem>

              <InfoItem label="Categoría">
                <select
                  value={category}
                  onChange={(e) => {
                    const prev = category;
                    setCategory(e.target.value);
                    patchTicket({ category: e.target.value }, () => setCategory(prev));
                  }}
                  disabled={updating}
                  className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-sm"
                >
                  <option value="billing">Facturación / Pagos</option>
                  <option value="technical">Problema técnico</option>
                  <option value="account">Cuenta / Acceso</option>
                  <option value="feature_request">Solicitud funcionalidad</option>
                  <option value="other">Otro</option>
                </select>
              </InfoItem>

              <InfoItem label="Asignado a">
                <select
                  value={assignedTo}
                  onChange={(e) => {
                    const prev = assignedTo;
                    setAssignedTo(e.target.value);
                    patchTicket({ assigned_to_id: e.target.value }, () => setAssignedTo(prev));
                  }}
                  disabled={updating}
                  className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-sm"
                >
                  <option value="">Sin asignar</option>
                  {staff.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name || s.email}
                    </option>
                  ))}
                </select>
              </InfoItem>

              <InfoItem label="Email contacto" value={ticket.contact_email} />
              <InfoItem label="Creado" value={formatDateTime(ticket.created_at)} />
              <InfoItem label="Actualizado" value={formatRelativeTime(ticket.updated_at)} suppressHydrationWarning />
              {ticket.resolved_at && (
                <InfoItem label="Resuelto" value={formatDateTime(ticket.resolved_at)} />
              )}
              {ticket.closed_at && (
                <InfoItem label="Cerrado" value={formatDateTime(ticket.closed_at)} />
              )}
              {ticket.created_by && (
                <InfoItem label="Creado por" value={`${ticket.created_by.name} (${ticket.created_by.email})`} />
              )}
            </div>
          </SectionCard>

          {/* Client info */}
          {ticket.business && (
            <SectionCard title="Cliente vinculado">
              <div className="space-y-2">
                <InfoItem label="Negocio" value={ticket.business.name} />
                <InfoItem label="Slug" value={ticket.business.slug} />
                <InfoItem label="Estado">
                  <StatusBadge label={statusLabel(ticket.business.status)} colorClass={statusColor(ticket.business.status)} />
                </InfoItem>
              </div>
            </SectionCard>
          )}

          {/* Subscription info */}
          {ticket.subscription && (
            <SectionCard title="Suscripción vinculada">
              <div className="space-y-2">
                <InfoItem label="Plan" value={planLabel(ticket.subscription.plan_code)} />
                <InfoItem label="Estado" value={ticket.subscription.status} />
                <InfoItem label="Provider" value={ticket.subscription.provider} />
                <InfoItem label="Vencimiento" value={formatDate(ticket.subscription.current_period_end)} />
              </div>
            </SectionCard>
          )}

          {/* Internal notes */}
          <SectionCard title="Notas internas del cliente" description="Notas del staff sobre este negocio">
            {ticket.business_notes.length > 0 ? (
              <div className="divide-y divide-slate-100">
                {ticket.business_notes.map((note) => (
                  <div key={note.id} className="py-3 first:pt-0">
                    <p className="text-sm text-slate-800 whitespace-pre-wrap">{note.body}</p>
                    <p className="mt-1 text-xs text-slate-500" suppressHydrationWarning>
                      {note.author_name} · {formatRelativeTime(note.created_at)}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-400">Sin notas internas.</p>
            )}
          </SectionCard>
        </div>
      </div>
    </div>
  );
}

// ── Helper ──────────────────────────────────────────────────────────────────

function InfoItem({
  label,
  value,
  children,
  suppressHydrationWarning: shw,
}: {
  label: string;
  value?: string;
  children?: React.ReactNode;
  suppressHydrationWarning?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-900" suppressHydrationWarning={shw}>{children ?? value ?? '—'}</dd>
    </div>
  );
}
