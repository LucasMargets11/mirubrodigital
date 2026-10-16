import { Phone } from 'lucide-react';

import { reviewReasonCopy } from '@/features/appointments/payment-display';
import type { Appointment } from '@/features/appointments/types';
import { timeInTimeZone } from '@/lib/business-time';

import { AppointmentActions, type AppointmentActionHandlers } from './appointment-actions';
import {
    AppointmentHoldNotice,
    AppointmentPaymentBadge,
    AppointmentStatusBadge,
    appointmentAccentClass,
    isInactiveStatus,
} from './appointment-status';

type DayViewProps = {
    appointments: Appointment[];
    /** Timezone IANA del Business: horas siempre en la zona del negocio (7D.1). */
    timeZone: string;
    highlightId?: string;
    /** Sin handlers (rol sin `manage_appointments`) no se muestran acciones. */
    actions?: AppointmentActionHandlers;
};

/**
 * Vista Día: agenda cronológica, una tarjeta por turno. El orden es el que
 * devuelve el backend (por `start_at`); acá no se filtra ni se reordena.
 */
export function DayView({ appointments, timeZone, highlightId, actions }: DayViewProps) {
    return (
        <ol className="space-y-2" aria-label="Turnos del día" data-testid="day-list">
            {appointments.map((appointment) => (
                <li key={appointment.id}>
                    <DayAppointmentCard
                        appointment={appointment}
                        timeZone={timeZone}
                        highlighted={appointment.id === highlightId}
                        actions={actions}
                    />
                </li>
            ))}
        </ol>
    );
}

function DayAppointmentCard({
    appointment,
    timeZone,
    highlighted,
    actions,
}: {
    appointment: Appointment;
    timeZone: string;
    highlighted: boolean;
    actions?: AppointmentActionHandlers;
}) {
    const start = timeInTimeZone(appointment.start_at, timeZone);
    const end = timeInTimeZone(appointment.end_at, timeZone);
    const summary = appointment.payment_summary;
    const inactive = isInactiveStatus(appointment.effective_status);

    const border = summary?.requires_review ? 'border-rose-300' : highlighted ? 'border-amber-300' : 'border-slate-200';
    const background = highlighted ? 'bg-amber-50' : inactive ? 'bg-slate-50' : 'bg-white';

    return (
        <article
            data-testid="appointment-card"
            aria-current={highlighted ? 'true' : undefined}
            aria-label={`${start} · ${appointment.customer_name}`}
            className={`relative grid grid-cols-[3.75rem,minmax(0,1fr)] gap-x-3 gap-y-3 rounded-xl border ${border} ${background} py-3 pl-4 pr-3 before:absolute before:inset-y-2 before:left-1.5 before:w-1 before:rounded-full ${appointmentAccentClass(appointment)} sm:grid-cols-[4.5rem,minmax(0,1fr),auto] sm:gap-x-4 sm:pl-5`}
        >
            <div className="tabular-nums">
                <p className={`text-lg font-semibold leading-tight ${inactive ? 'text-slate-500' : 'text-slate-900'}`}>{start}</p>
                <p className="text-xs text-slate-500">
                    <span className="sr-only">Termina a las </span>
                    <span>{end}</span>
                </p>
            </div>

            <div className="min-w-0 space-y-2">
                <div className="min-w-0">
                    <p className={`truncate text-base font-semibold ${inactive ? 'text-slate-600' : 'text-slate-900'}`}>
                        {appointment.customer_name}
                    </p>
                    <p className="truncate text-sm text-slate-600">
                        {appointment.service_name}
                        <span aria-hidden="true"> · </span>
                        <span className="sr-only">, profesional: </span>
                        {appointment.professional?.name ?? <span className="text-slate-400">Sin asignar</span>}
                    </p>
                    <a
                        href={`tel:${appointment.customer_phone}`}
                        className="mt-0.5 inline-flex items-center gap-1 rounded text-xs text-slate-500 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900"
                    >
                        <Phone className="h-3 w-3" aria-hidden="true" />
                        <span className="sr-only">Llamar al </span>
                        {appointment.customer_phone}
                    </a>
                </div>

                <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
                    <span className="sr-only">Estado del turno:</span>
                    <AppointmentStatusBadge appointment={appointment} />
                    <AppointmentHoldNotice appointment={appointment} timeZone={timeZone} />
                    {summary ? (
                        <>
                            <span className="sr-only">Pago:</span>
                            <AppointmentPaymentBadge appointment={appointment} />
                        </>
                    ) : null}
                </div>
                {summary?.requires_review ? (
                    <p className="max-w-prose text-xs text-rose-700">{reviewReasonCopy(summary.review_reason)}</p>
                ) : null}
            </div>

            {actions ? (
                <div className="col-start-2 sm:col-start-3 sm:row-start-1 sm:self-start">
                    <AppointmentActions appointment={appointment} timeLabel={start} handlers={actions} />
                </div>
            ) : null}
        </article>
    );
}
