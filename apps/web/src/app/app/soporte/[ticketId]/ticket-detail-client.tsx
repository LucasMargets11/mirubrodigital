"use client";

import { useState } from 'react';
import Link from 'next/link';
import type { Route } from 'next';

import { apiPost, ApiError } from '@/lib/api/client';
import { ticketStatusColor, ticketCategoryLabel } from '@/lib/admin/display';

import type { TenantTicketDetail, TenantTicketMessage } from '../types';

const TENANT_STATUS_LABELS: Record<string, string> = {
  open: 'Abierto',
  in_progress: 'En curso',
  waiting_on_client: 'Te respondimos',
  resolved: 'Resuelto',
  closed: 'Cerrado',
};

function tenantStatusLabel(status: string): string {
  return TENANT_STATUS_LABELS[status] ?? status;
}

function formatDateTime(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('es-AR', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

type TicketDetailClientProps = {
  initialTicket: TenantTicketDetail;
};

export function TicketDetailClient({ initialTicket }: TicketDetailClientProps) {
  const [ticket, setTicket] = useState(initialTicket);
  const [replyBody, setReplyBody] = useState('');
  const [sending, setSending] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isClosed = ticket.status === 'closed';

  const handleReply = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = replyBody.trim();
    if (!trimmed || sending) return;

    setSending(true);
    setError(null);

    try {
      const msg = await apiPost<TenantTicketMessage>(
        `/api/v1/support/tickets/${ticket.id}/reply/`,
        { body: trimmed },
      );
      setTicket((prev) => ({
        ...prev,
        messages: [...prev.messages, msg],
        // If was waiting/resolved, auto-reopens to open
        status: ['waiting_on_client', 'resolved'].includes(prev.status) ? 'open' : prev.status,
        can_close: true,
        can_reopen: false,
      }));
      setReplyBody('');
    } catch (err) {
      if (err instanceof ApiError) {
        const detail = (err.payload as { detail?: string })?.detail;
        setError(detail ?? 'Error al enviar la respuesta.');
      } else {
        setError('Error inesperado.');
      }
    } finally {
      setSending(false);
    }
  };

  const handleCloseReopen = async (action: 'close' | 'reopen') => {
    setActionLoading(true);
    setError(null);

    try {
      const res = await apiPost<{ id: string; status: string; closed_at?: string }>(
        `/api/v1/support/tickets/${ticket.id}/close/`,
        { action },
      );
      setTicket((prev) => ({
        ...prev,
        status: res.status,
        can_close: action === 'reopen',
        can_reopen: action === 'close',
      }));
    } catch (err) {
      if (err instanceof ApiError) {
        const detail = (err.payload as { detail?: string })?.detail;
        setError(detail ?? 'Error al cambiar el estado.');
      } else {
        setError('Error inesperado.');
      }
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <section className="space-y-6">
      {/* Back + header */}
      <div>
        <Link href={'/app/soporte' as Route} className="text-sm text-brand-600 hover:underline">
          ← Volver a Soporte
        </Link>
      </div>

      <header className="flex flex-col gap-3 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm md:flex-row md:items-start md:justify-between">
        <div className="space-y-1">
          <p className="font-mono text-xs text-slate-400">{ticket.reference}</p>
          <h1 className="text-2xl font-semibold text-slate-900">{ticket.subject}</h1>
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
            <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${ticketStatusColor(ticket.status)}`}>
              {tenantStatusLabel(ticket.status)}
            </span>
            <span>·</span>
            <span>{ticketCategoryLabel(ticket.category)}</span>
            <span>·</span>
            <span>Creado {formatDateTime(ticket.created_at)}</span>
          </div>
        </div>

        <div className="flex gap-2">
          {ticket.can_close && (
            <button
              type="button"
              disabled={actionLoading}
              onClick={() => handleCloseReopen('close')}
              className="rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              Cerrar ticket
            </button>
          )}
          {ticket.can_reopen && (
            <button
              type="button"
              disabled={actionLoading}
              onClick={() => handleCloseReopen('reopen')}
              className="rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              Reabrir ticket
            </button>
          )}
        </div>
      </header>

      {error && (
        <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
          {error}
        </p>
      )}

      {/* Messages thread */}
      <div className="space-y-4">
        {ticket.messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
      </div>

      {/* Reply form */}
      {!isClosed ? (
        <form onSubmit={handleReply} className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <label htmlFor="reply-body" className="mb-2 block text-sm font-medium text-slate-700">
            Responder
          </label>
          <textarea
            id="reply-body"
            value={replyBody}
            onChange={(e) => setReplyBody(e.target.value)}
            rows={4}
            maxLength={5000}
            placeholder="Escribí tu mensaje…"
            className="w-full resize-y rounded-2xl border border-slate-200 px-4 py-2.5 text-sm focus:border-slate-900 focus:outline-none"
          />
          <div className="mt-3 flex items-center justify-between">
            <p className="text-xs text-slate-400">{replyBody.length} / 5000</p>
            <button
              type="submit"
              disabled={!replyBody.trim() || sending}
              className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {sending ? 'Enviando…' : 'Enviar'}
            </button>
          </div>
        </form>
      ) : (
        <div className="rounded-2xl border border-dashed border-slate-200 px-6 py-8 text-center text-sm text-slate-500">
          Este ticket está cerrado. Podés{' '}
          <button
            type="button"
            onClick={() => handleCloseReopen('reopen')}
            disabled={actionLoading}
            className="text-brand-600 underline disabled:opacity-50"
          >
            reabrirlo
          </button>{' '}
          para seguir la conversación.
        </div>
      )}
    </section>
  );
}

function MessageBubble({ message }: { message: TenantTicketMessage }) {
  const isStaff = message.is_from_staff;

  return (
    <article
      className={`rounded-2xl border p-4 ${
        isStaff
          ? 'border-brand-100 bg-brand-50'
          : 'border-slate-200 bg-white'
      }`}
    >
      <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
        <span className="font-semibold text-slate-700">{message.author_name}</span>
        {isStaff && (
          <span className="rounded-full bg-brand-100 px-2 py-0.5 text-[10px] font-semibold text-brand-700">
            Soporte
          </span>
        )}
        <span>·</span>
        <span>{formatDateTime(message.created_at)}</span>
      </div>
      <p className="whitespace-pre-wrap text-sm text-slate-800">{message.body}</p>
    </article>
  );
}
