import { useMemo } from 'react';

import type { Appointment } from '@/features/appointments/types';
import { WEEKDAY_SHORT, formatAppointmentCount, formatWeekdayLabel, groupAppointmentsByDay, type WeekRange } from '@/features/appointments/week';
import { calendarParts, isoWeekdayIndex, timeInTimeZone, todayInTimeZone } from '@/lib/business-time';

import {
    AppointmentPaymentBadge,
    AppointmentStatusBadge,
    appointmentAccentClass,
    isInactiveStatus,
} from './appointment-status';

type WeekViewProps = {
    range: WeekRange;
    appointments: Appointment[];
    /** Timezone IANA del Business: agrupación por día y horas (7D.1). */
    timeZone: string;
    highlightId?: string;
    /** Abre el mismo modal de detalle/edición que la vista Día; sin él, las tarjetas no son clickeables. */
    onOpen?: (appointment: Appointment) => void;
};

/**
 * Vista semanal (Slice 7D, rediseño UI 01): lunes → domingo.
 * - mobile (< md): días apilados; los días vacíos se reducen a una línea.
 * - tablet (md–xl): 7 columnas con ancho mínimo y scroll horizontal.
 * - desktop (xl+): 7 columnas sin scroll.
 * Solo consulta: los estados salen tal cual del backend (7B.3).
 */
export function WeekView({ range, appointments, timeZone, highlightId, onOpen }: WeekViewProps) {
    const byDay = useMemo(
        () => groupAppointmentsByDay(appointments, range.days, timeZone),
        [appointments, range.days, timeZone],
    );
    const today = todayInTimeZone(timeZone);

    return (
        <div className="-mx-1 overflow-x-auto px-1 pb-1">
            <div className="grid grid-cols-1 gap-2 md:min-w-[56rem] md:grid-cols-7 xl:min-w-0" data-testid="week-grid">
                {range.days.map((day) => {
                    const dayAppointments = byDay[day];
                    const isToday = day === today;
                    const isEmpty = dayAppointments.length === 0;
                    return (
                        <section
                            key={day}
                            aria-label={formatWeekdayLabel(day)}
                            aria-current={isToday ? 'date' : undefined}
                            data-testid={`week-day-${day}`}
                            className={`min-w-0 rounded-xl border p-2 ${
                                isToday ? 'border-slate-900/70 bg-white shadow-sm ring-1 ring-slate-900/10' : 'border-slate-100 bg-slate-50/70'
                            } ${isEmpty ? 'flex items-center justify-between gap-2 md:block' : ''}`}
                        >
                            <h3 className="flex items-center gap-2 px-1 md:mb-2 md:flex-col md:items-start md:gap-0.5">
                                <span className="flex items-baseline gap-1.5">
                                    <span
                                        className={`text-xs font-semibold uppercase tracking-wide ${isToday ? 'text-slate-900' : 'text-slate-500'}`}
                                    >
                                        {WEEKDAY_SHORT[isoWeekdayIndex(day)]}
                                    </span>
                                    <span className={`text-lg font-semibold leading-none tabular-nums ${isToday ? 'text-slate-900' : 'text-slate-700'}`}>
                                        {calendarParts(day).day}
                                    </span>
                                    {isToday ? (
                                        <span className="rounded-full bg-slate-900 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
                                            Hoy
                                        </span>
                                    ) : null}
                                </span>
                                {!isEmpty ? (
                                    <span className="text-xs font-normal text-slate-500">{formatAppointmentCount(dayAppointments.length)}</span>
                                ) : null}
                            </h3>
                            {isEmpty ? (
                                <p className="px-1 text-xs text-slate-400">Sin turnos</p>
                            ) : (
                                <ul className="mt-2 space-y-1.5 md:mt-0">
                                    {dayAppointments.map((appointment) => (
                                        <li key={appointment.id}>
                                            <WeekAppointmentCard
                                                appointment={appointment}
                                                timeZone={timeZone}
                                                highlighted={appointment.id === highlightId}
                                                onOpen={onOpen}
                                            />
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </section>
                    );
                })}
            </div>
        </div>
    );
}

function WeekAppointmentCard({
    appointment,
    timeZone,
    highlighted,
    onOpen,
}: {
    appointment: Appointment;
    timeZone: string;
    highlighted: boolean;
    onOpen?: (appointment: Appointment) => void;
}) {
    const inactive = isInactiveStatus(appointment.effective_status);
    const border = appointment.payment_summary?.requires_review
        ? 'border-rose-300'
        : highlighted
          ? 'border-amber-300'
          : 'border-slate-200';
    const background = highlighted ? 'bg-amber-50' : inactive ? 'bg-slate-50' : 'bg-white';
    const className = `relative block w-full rounded-lg border ${border} ${background} py-1.5 pl-3 pr-2 text-left text-xs text-slate-700 before:absolute before:inset-y-1.5 before:left-1 before:w-[3px] before:rounded-full ${appointmentAccentClass(appointment)}`;

    const content = (
        <>
            <span className="block font-semibold tabular-nums text-slate-900">{timeInTimeZone(appointment.start_at, timeZone)}</span>
            <span className={`block truncate font-medium ${inactive ? 'text-slate-500' : 'text-slate-800'}`}>{appointment.customer_name}</span>
            <span className="block truncate text-slate-500">{appointment.service_name}</span>
            {appointment.professional ? <span className="block truncate text-slate-400">{appointment.professional.name}</span> : null}
            <span className="mt-1.5 flex flex-wrap items-start gap-1">
                <AppointmentStatusBadge appointment={appointment} />
                <AppointmentPaymentBadge appointment={appointment} />
            </span>
        </>
    );

    if (!onOpen) {
        return (
            <div className={className} aria-current={highlighted ? 'true' : undefined} data-testid="week-appointment">
                {content}
            </div>
        );
    }
    return (
        <button
            type="button"
            onClick={() => onOpen(appointment)}
            aria-current={highlighted ? 'true' : undefined}
            data-testid="week-appointment"
            className={`${className} hover:border-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900`}
        >
            {content}
        </button>
    );
}
