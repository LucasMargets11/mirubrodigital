"use client";

import { useState } from 'react';
import Link from 'next/link';
import type { Route } from 'next';

import { ticketStatusColor, ticketCategoryLabel } from '@/lib/admin/display';

import type { TenantTicketList, TenantTicketRow } from './types';

// Tenant-friendly status labels (differ from admin wording)
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

const STATUS_FILTERS = [
  { id: '', label: 'Todos' },
  { id: 'open', label: 'Abiertos' },
  { id: 'in_progress', label: 'En curso' },
  { id: 'waiting_on_client', label: 'Con respuesta' },
  { id: 'resolved', label: 'Resueltos' },
  { id: 'closed', label: 'Cerrados' },
];

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('es-AR', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

type SoporteClientProps = {
  initialTickets: TenantTicketList | null;
  fetchError?: boolean;
};

export function SoporteClient({ initialTickets, fetchError }: SoporteClientProps) {
  const [activeFilter, setActiveFilter] = useState('');

  const tickets = initialTickets?.results ?? [];

  const filtered = activeFilter
    ? tickets.filter((t) => t.status === activeFilter)
    : tickets;

  return (
    <section className="space-y-6">
      {/* Header */}
      <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-400">Cuenta</p>
          <h1 className="text-3xl font-semibold text-slate-900">Soporte</h1>
          <p className="text-sm text-slate-500">Consultá el estado de tus tickets o enviá uno nuevo.</p>
        </div>
        <Link
          href={'/app/soporte/nuevo' as Route}
          className="self-start rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800"
        >
          Nuevo ticket
        </Link>
      </header>

      {/* Status filter tabs */}
      <div className="flex flex-wrap gap-2">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setActiveFilter(f.id)}
            className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${
              activeFilter === f.id
                ? 'border-slate-900 bg-slate-900 text-white'
                : 'border-slate-200 bg-white text-slate-600 hover:border-slate-900 hover:text-slate-900'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Tickets list */}
      <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
        {fetchError && (
          <p className="mb-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
            No pudimos cargar tus tickets. Intentá recargar la página.
          </p>
        )}

        <p className="mb-4 text-xs uppercase tracking-wide text-slate-400">
          {filtered.length} {filtered.length === 1 ? 'ticket' : 'tickets'}
        </p>

        {filtered.length === 0 && !fetchError ? (
          <div className="rounded-2xl border border-dashed border-slate-200 px-6 py-12 text-center">
            <p className="text-base font-semibold text-slate-900">Sin tickets en esta vista</p>
            <p className="mt-2 text-sm text-slate-500">
              {activeFilter ? 'Probá con otro filtro o' : 'Todavía no tenés tickets.'}{' '}
              <Link href={'/app/soporte/nuevo' as Route} className="text-brand-600 underline">
                Crear un ticket
              </Link>
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-3 py-2">Ref.</th>
                  <th className="px-3 py-2">Asunto</th>
                  <th className="px-3 py-2">Categoría</th>
                  <th className="px-3 py-2">Estado</th>
                  <th className="px-3 py-2">Creado</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map((ticket) => (
                  <TicketRow key={ticket.id} ticket={ticket} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

function TicketRow({ ticket }: { ticket: TenantTicketRow }) {
  return (
    <tr className="hover:bg-slate-50">
      <td className="px-3 py-3">
        <span className="font-mono text-xs font-medium text-brand-600">{ticket.reference}</span>
      </td>
      <td className="px-3 py-3">
        <div className="flex items-center gap-2">
          <span className="font-medium text-slate-900">{ticket.subject}</span>
          {ticket.has_staff_reply && ticket.status !== 'closed' && (
            <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-semibold text-violet-700">
              Nueva respuesta
            </span>
          )}
        </div>
      </td>
      <td className="px-3 py-3 text-slate-600">{ticketCategoryLabel(ticket.category)}</td>
      <td className="px-3 py-3">
        <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${ticketStatusColor(ticket.status)}`}>
          {tenantStatusLabel(ticket.status)}
        </span>
      </td>
      <td className="px-3 py-3 text-slate-500">{formatDate(ticket.created_at)}</td>
      <td className="px-3 py-3 text-right">
        <Link
          href={`/app/soporte/${ticket.id}` as Route}
          className="text-sm font-medium text-brand-600 hover:underline"
        >
          Ver
        </Link>
      </td>
    </tr>
  );
}
