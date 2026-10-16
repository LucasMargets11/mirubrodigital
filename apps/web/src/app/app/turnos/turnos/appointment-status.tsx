import {
    AlertTriangle,
    BadgeCheck,
    Check,
    CheckCheck,
    CircleSlash,
    Clock,
    Hourglass,
    UserX,
    X,
    type LucideIcon,
} from 'lucide-react';

import { paymentBadge, reviewReasonCopy, type PaymentBadgeTone } from '@/features/appointments/payment-display';
import type { Appointment, AppointmentStatus } from '@/features/appointments/types';
import { dateTimeInTimeZone, timeInTimeZone } from '@/lib/business-time';
import { formatARS } from '@/lib/format';

/* Estado del turno: pill rellena + ícono (nunca solo color). */
const STATUS_STYLES: Record<AppointmentStatus, { badge: string; accent: string; icon: LucideIcon }> = {
    confirmed: { badge: 'bg-emerald-50 text-emerald-700 ring-emerald-200', accent: 'before:bg-emerald-500', icon: Check },
    pending_payment: { badge: 'bg-amber-50 text-amber-800 ring-amber-200', accent: 'before:bg-amber-400', icon: Clock },
    completed: { badge: 'bg-slate-100 text-slate-700 ring-slate-200', accent: 'before:bg-slate-400', icon: CheckCheck },
    no_show: { badge: 'bg-orange-50 text-orange-700 ring-orange-200', accent: 'before:bg-orange-400', icon: UserX },
    cancelled: { badge: 'bg-slate-100 text-slate-500 ring-slate-200', accent: 'before:bg-slate-300', icon: X },
    expired: { badge: 'bg-slate-50 text-slate-500 ring-slate-200', accent: 'before:bg-slate-200', icon: Hourglass },
};

const FALLBACK_STATUS_STYLE = { badge: 'bg-slate-100 text-slate-600 ring-slate-200', accent: 'before:bg-slate-300', icon: Clock };

/* Estado del pago: chip con borde (forma distinta a la del estado del turno). */
const PAYMENT_TONE_STYLES: Record<PaymentBadgeTone, { badge: string; icon: LucideIcon }> = {
    paid: { badge: 'border-emerald-200 bg-white text-emerald-700', icon: BadgeCheck },
    review: { badge: 'border-rose-300 bg-rose-50 text-rose-700', icon: AlertTriangle },
    warning: { badge: 'border-amber-200 bg-white text-amber-800', icon: Clock },
    muted: { badge: 'border-slate-200 bg-white text-slate-500', icon: CircleSlash },
};

/** Estados que ya no requieren acción: la tarjeta se muestra atenuada. */
export function isInactiveStatus(status: AppointmentStatus): boolean {
    return status === 'cancelled' || status === 'expired';
}

/**
 * Clase de la barra lateral de color de una tarjeta (pseudo-elemento `before:`).
 * Un pago en revisión manda sobre el estado del turno.
 */
export function appointmentAccentClass(appointment: Appointment): string {
    if (appointment.payment_summary?.requires_review) return 'before:bg-rose-500';
    return (STATUS_STYLES[appointment.effective_status] ?? FALLBACK_STATUS_STYLE).accent;
}

/** Badge del estado operativo efectivo (`effective_status` del backend). */
export function AppointmentStatusBadge({
    appointment,
}: {
    appointment: Pick<Appointment, 'effective_status' | 'effective_status_display'>;
}) {
    const style = STATUS_STYLES[appointment.effective_status] ?? FALLBACK_STATUS_STYLE;
    const Icon = style.icon;
    return (
        <span
            data-testid="appointment-status"
            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${style.badge}`}
        >
            <Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
            {appointment.effective_status_display}
        </span>
    );
}

/** Badge financiero (`payment_summary`), o nada si nunca hubo intento de pago. */
export function AppointmentPaymentBadge({ appointment }: { appointment: Pick<Appointment, 'payment_summary'> }) {
    const summary = appointment.payment_summary;
    const badge = paymentBadge(summary);
    if (!badge || !summary) return null;
    const style = PAYMENT_TONE_STYLES[badge.tone];
    const Icon = style.icon;
    return (
        <span
            data-testid="appointment-payment"
            data-tone={badge.tone}
            className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold ${style.badge}`}
        >
            <Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
            {badge.label}
            {badge.showAmount ? ` · ${formatARS(summary.amount)}` : ''}
        </span>
    );
}

/** "Reserva hasta HH:MM" mientras el hold de `pending_payment` sigue activo. */
export function AppointmentHoldNotice({ appointment, timeZone }: { appointment: Appointment; timeZone: string }) {
    if (appointment.effective_status !== 'pending_payment' || !appointment.expires_at) return null;
    return <span className="text-xs text-slate-500">Reserva hasta {timeInTimeZone(appointment.expires_at, timeZone)}</span>;
}

/** Sección "Pago" del detalle del turno (modal de edición). */
export function AppointmentPaymentSection({ appointment, timeZone }: { appointment: Appointment; timeZone: string }) {
    const summary = appointment.payment_summary;
    const badge = paymentBadge(summary);
    if (!summary || !badge) return null;

    return (
        <section
            aria-label="Pago"
            className={`rounded-xl border px-4 py-3 text-sm ${summary.requires_review ? 'border-rose-300 bg-rose-50' : 'border-slate-200 bg-slate-50'}`}
        >
            <h3 className="mb-2 text-sm font-semibold text-slate-800">Pago</h3>
            <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1 text-slate-600">
                <dt>Estado</dt>
                <dd className="font-medium text-slate-800">{badge.label}</dd>
                <dt>Seña</dt>
                <dd>{formatARS(summary.amount)}</dd>
                {summary.paid_at ? (
                    <>
                        <dt>Fecha de pago</dt>
                        <dd>{dateTimeInTimeZone(summary.paid_at, timeZone)}</dd>
                    </>
                ) : null}
            </dl>
            {summary.requires_review ? (
                <p role="note" className="mt-2 text-xs text-rose-700">
                    {reviewReasonCopy(summary.review_reason)} Revisá el caso y contactá al cliente.
                </p>
            ) : null}
        </section>
    );
}
