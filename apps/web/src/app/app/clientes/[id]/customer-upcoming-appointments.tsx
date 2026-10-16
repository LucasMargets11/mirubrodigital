"use client";

import Link from 'next/link';

import { AppointmentPaymentBadge, AppointmentStatusBadge, isInactiveStatus } from '@/app/app/turnos/turnos/appointment-status';
import { useCustomerAppointments } from '@/features/customers/hooks';
import type { CustomerAppointmentHistoryItem } from '@/features/customers/types';
import { calendarParts, dateInTimeZone, isoWeekdayIndex, timeInTimeZone } from '@/lib/business-time';
import { formatARS } from '@/lib/format';

const UPCOMING_LIMIT = 25;

export const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
const WEEKDAYS = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom'];

/** Deep link existente de la agenda (Slice 6D): día del turno en la zona del Business. */
export function agendaHref(appointment: { id: string; start_at: string }, timeZone: string) {
    return `/app/turnos/turnos?date=${dateInTimeZone(appointment.start_at, timeZone)}&appointment=${appointment.id}`;
}

/** "vie 02 oct 2026 · 11:15" en la zona del Business (nunca la del navegador). */
export function formatAppointmentWhen(iso: string, timeZone: string) {
    const day = dateInTimeZone(iso, timeZone);
    const { year, monthIndex, day: dayOfMonth } = calendarParts(day);
    const dd = String(dayOfMonth).padStart(2, '0');
    return `${WEEKDAYS[isoWeekdayIndex(day)]} ${dd} ${MONTHS[monthIndex]} ${year} · ${timeInTimeZone(iso, timeZone)}`;
}

/**
 * Próximos turnos del cliente (Turnos CUSTOMER 03 → 04A): la partición viene
 * del backend (`customer_history.py`, scope `upcoming`). Lo ya ocurrido
 * (incluidos cancelados, no-shows y vencidos) vive en la timeline unificada
 * (`customer-timeline.tsx`); acá solo lo que ocupa agenda a futuro.
 */
export function CustomerUpcomingAppointments({ customerId, timeZone }: { customerId: string; timeZone: string }) {
    const upcomingQuery = useCustomerAppointments(customerId, { scope: 'upcoming', limit: UPCOMING_LIMIT });

    const upcoming = upcomingQuery.data?.results ?? [];
    const upcomingCount = upcomingQuery.data?.count ?? 0;

    let body;
    if (upcomingQuery.isLoading) {
        body = <p className="text-sm text-slate-500">Cargando turnos...</p>;
    } else if (upcomingQuery.isError) {
        body = <p className="text-sm text-rose-600">No pudimos cargar los turnos del cliente.</p>;
    } else if (upcomingCount === 0) {
        // La tarjeta "Próximo turno" del resumen ya dice "Sin turnos próximos.".
        return null;
    } else {
        body = (
            <>
                <AppointmentList items={upcoming} timeZone={timeZone} />
                {upcomingCount > upcoming.length ? (
                    <p className="pt-2 text-xs text-slate-500">y {upcomingCount - upcoming.length} más en la agenda.</p>
                ) : null}
            </>
        );
    }

    return (
        <section aria-label="Próximos turnos" className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
            <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Próximos turnos
                {upcomingCount > 0 ? <span className="text-slate-300"> · {upcomingCount}</span> : null}
            </h3>
            {body}
        </section>
    );
}

function AppointmentList({ items, timeZone }: { items: CustomerAppointmentHistoryItem[]; timeZone: string }) {
    return (
        <ul className="mt-2 divide-y divide-slate-100 rounded-2xl border border-slate-100">
            {items.map((item) => (
                <li
                    key={item.id}
                    data-testid="customer-appointment"
                    className={`flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between ${isInactiveStatus(item.status) ? 'opacity-70' : ''}`}
                >
                    <div className="min-w-0 space-y-0.5">
                        <p className="text-sm font-semibold text-slate-900">{formatAppointmentWhen(item.start_at, timeZone)}</p>
                        <p className="text-sm text-slate-700">
                            {item.service_name}
                            {item.professional_name ? <span className="text-slate-500"> · {item.professional_name}</span> : null}
                        </p>
                        <div className="flex flex-wrap items-center gap-1.5 pt-1">
                            <AppointmentStatusBadge
                                appointment={{ effective_status: item.status, effective_status_display: item.status_display }}
                            />
                            <AppointmentPaymentBadge appointment={item} />
                            {item.source === 'public' ? (
                                <span className="rounded-md bg-slate-50 px-2 py-0.5 text-xs text-slate-500">Reserva online</span>
                            ) : null}
                        </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-4 sm:flex-col sm:items-end sm:gap-1">
                        {Number(item.service_price) > 0 ? (
                            <span className="text-sm font-semibold text-slate-700">{formatARS(item.service_price)}</span>
                        ) : null}
                        <Link
                            href={agendaHref(item, timeZone) as any}
                            className="text-xs font-semibold text-slate-500 hover:text-slate-900"
                        >
                            Ver en agenda
                        </Link>
                    </div>
                </li>
            ))}
        </ul>
    );
}
