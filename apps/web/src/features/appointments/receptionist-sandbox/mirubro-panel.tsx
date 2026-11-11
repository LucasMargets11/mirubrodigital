'use client';

import { Check, Circle, PanelsTopLeft } from 'lucide-react';

import { Card } from '@/components/ui/card';

import type { MirubroActivity, MirubroSnapshot } from './types';

type MiRubroPanelProps = {
  snapshot: MirubroSnapshot;
};

const LEAD_STATUS_LABELS: Record<Exclude<MirubroSnapshot['lead']['status'], 'empty'>, string> = {
  new: 'Nuevo',
  qualified: 'Calificado',
  converted: 'Convertido',
};

const ACTIVITY_STATUS_LABELS: Record<MirubroActivity['status'], string> = {
  pending: 'Pendiente',
  active: 'En curso',
  completed: 'Completado',
};

function activityIcon(status: MirubroActivity['status']) {
  if (status === 'completed')
    return (
      <Check className="receptionist-check-enter h-3.5 w-3.5 text-emerald-600" aria-hidden="true" />
    );
  if (status === 'active')
    return <span className="h-2 w-2 shrink-0 rounded-full bg-amber-500" aria-hidden="true" />;
  return <Circle className="h-3.5 w-3.5 text-slate-300" aria-hidden="true" />;
}

export function MiRubroPanel({ snapshot }: MiRubroPanelProps) {
  const { contact, lead, booking, events } = snapshot;

  return (
    <section
      aria-label="Procesamiento en MiRubro"
      className="min-w-0 space-y-3 rounded-2xl border border-emerald-200 bg-emerald-50/80 p-3"
      data-testid="mirubro-panel"
    >
      <header className="flex items-center gap-2 px-1 py-1">
        <PanelsTopLeft
          className="h-8 w-8 shrink-0 rounded-xl bg-emerald-700 p-1.5 text-white"
          aria-hidden="true"
        />
        <div className="min-w-0">
          <h2 className="text-sm font-bold text-emerald-950">MiRubro</h2>
          <p className="text-xs text-emerald-800">Tu negocio, actualizado</p>
        </div>
      </header>

      <Card
        key={`contact-${contact.status}-${contact.name ?? ''}`}
        className={`min-h-[110px] min-w-0 rounded-xl border-emerald-100 bg-white p-3 shadow-sm ${contact.status === 'identified' ? 'receptionist-card-update' : ''}`}
        data-testid="mirubro-contact-card"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-800">Contacto</h3>
          {contact.status === 'identified' ? (
            <div className="flex shrink-0 items-center gap-1.5">
              <span className="rounded-full bg-emerald-100 px-2 py-1 text-[11px] font-semibold text-emerald-800">
                Identificado
              </span>
            </div>
          ) : null}
        </div>
        {contact.status === 'empty' ? (
          <p className="mt-3 text-xs text-slate-500">Todavía no identificado</p>
        ) : (
          <div className="mt-3 flex min-w-0 items-center gap-2">
            <span
              aria-hidden="true"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-emerald-100 text-sm font-semibold text-emerald-800"
            >
              {contact.name?.charAt(0).toUpperCase()}
            </span>
            <div className="min-w-0 flex-1">
              <p className="break-words text-sm font-semibold text-slate-800">{contact.name}</p>
              <p className="break-all text-xs text-slate-600">{contact.phone}</p>
              <p className="text-[10px] text-slate-500">WhatsApp</p>
            </div>
          </div>
        )}
      </Card>

      <Card
        key={`lead-${lead.status}-${lead.preferredDay ?? ''}`}
        className={`min-h-[116px] min-w-0 rounded-xl border-emerald-100 bg-white p-3 shadow-sm ${lead.status !== 'empty' ? 'receptionist-card-update' : ''}`}
        data-testid="mirubro-lead-card"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-800">Lead</h3>
          {lead.status !== 'empty' ? (
            <div className="flex shrink-0 items-center gap-1.5">
              <span
                className={`rounded-full px-2 py-1 text-[11px] font-semibold ${lead.status === 'converted' ? 'bg-emerald-100 text-emerald-800' : lead.status === 'qualified' ? 'bg-blue-100 text-blue-800' : 'bg-sky-100 text-sky-800'}`}
              >
                {LEAD_STATUS_LABELS[lead.status]}
              </span>
            </div>
          ) : null}
        </div>
        {lead.status === 'empty' ? (
          <p className="mt-3 text-xs text-slate-500">Todavía no creado</p>
        ) : (
          <div className="mt-3 min-w-0 space-y-1">
            <p className="break-words text-xs font-semibold text-slate-800">
              Reservar turno · {lead.service}
            </p>
            {lead.preferredDay && lead.preferredTimeRange ? (
              <p className="break-words text-xs text-slate-600">
                Preferencia: {lead.preferredDay} · {lead.preferredTimeRange}
              </p>
            ) : null}
            <p className="text-[10px] text-slate-500">WhatsApp</p>
          </div>
        )}
      </Card>

      <Card
        key={`booking-${booking.status}-${booking.slot ?? ''}`}
        className={`min-h-[100px] min-w-0 rounded-xl bg-white p-3 shadow-sm ${booking.status === 'confirmed' ? 'receptionist-card-update border-emerald-300' : booking.status === 'pending' ? 'receptionist-card-update border-amber-200' : 'border-emerald-100'}`}
        data-testid="mirubro-booking-card"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-800">Reserva</h3>
          {booking.status !== 'empty' ? (
            <span
              className={`shrink-0 rounded-full px-2 py-1 text-[11px] font-semibold ${
                booking.status === 'confirmed'
                  ? 'bg-emerald-100 text-emerald-800'
                  : 'bg-amber-100 text-amber-800'
              }`}
            >
              {booking.status === 'confirmed' ? 'Confirmada' : 'Pendiente'}
            </span>
          ) : null}
        </div>
        {booking.status === 'empty' ? (
          <p className="mt-3 text-xs text-slate-500">Sin turno</p>
        ) : (
          <div className="mt-3 flex min-w-0 flex-wrap items-center gap-1 text-xs text-slate-700">
            <span className="break-words font-semibold">{booking.service}</span>
            <span aria-hidden="true">·</span>
            <span className="min-w-0 break-words">
              {booking.day}
              {booking.slot ? ` · ${booking.slot}` : ''}
            </span>
            {booking.status === 'confirmed' ? (
              <Check
                className="receptionist-check-enter ml-auto h-3.5 w-3.5 shrink-0 text-emerald-600"
                aria-hidden="true"
              />
            ) : null}
          </div>
        )}
      </Card>

      <div className="min-h-[258px] min-w-0 rounded-xl border border-emerald-100 bg-white p-3">
        <h3 className="text-sm font-semibold text-slate-800">Actividad de MiRubro</h3>
        {events.length ? (
          <ol aria-label="Actividad de MiRubro" className="mt-3 space-y-2">
            {events.map((event) => (
              <li
                key={`${event.id}-${event.status}`}
                data-testid="mirubro-activity-event"
                data-event-status={event.status}
                aria-current={event.status === 'active' ? 'step' : undefined}
                aria-label={`${event.label}: ${ACTIVITY_STATUS_LABELS[event.status]}`}
                className={`receptionist-activity-enter flex min-w-0 items-start gap-2 rounded-lg px-2 py-1.5 text-xs leading-4 ${event.status === 'active' ? 'bg-amber-50 text-amber-900 ring-1 ring-inset ring-amber-200' : 'bg-emerald-50/60 text-slate-700'}`}
              >
                {activityIcon(event.status)}
                <span className="min-w-0 flex-1 break-words">
                  {event.label}
                  <span
                    className={`block text-[10px] ${event.status === 'active' ? 'font-semibold text-amber-700' : 'text-emerald-700'}`}
                  >
                    {ACTIVITY_STATUS_LABELS[event.status]}
                  </span>
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="mt-3 text-xs text-slate-500">Sin actividad todavía</p>
        )}
      </div>
    </section>
  );
}
