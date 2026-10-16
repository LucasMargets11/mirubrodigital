/* ── Presentación del estado financiero de un turno (Slice 7B.3) ─────────
 * Solo copy y tonos: QUÉ intento de pago representa al turno y cuál es el
 * estado operativo efectivo los decide el backend (`payment_summary`,
 * `effective_status`). Acá no se reimplementa ninguna regla financiera.
 */
import type {
    AppointmentPaymentReviewReason,
    AppointmentPaymentStatus,
    AppointmentPaymentSummary,
} from './types';

export type PaymentBadgeTone = 'paid' | 'review' | 'warning' | 'muted';

export type PaymentBadge = {
    label: string;
    tone: PaymentBadgeTone;
    /** Si corresponde mostrar el importe de la seña junto al badge. */
    showAmount: boolean;
};

const PAYMENT_BADGES: Record<AppointmentPaymentStatus, PaymentBadge> = {
    approved: { label: 'Pagado', tone: 'paid', showAmount: true },
    requires_review: { label: 'Pago recibido · Requiere revisión', tone: 'review', showAmount: true },
    uncertain: { label: 'Pago en verificación', tone: 'warning', showAmount: false },
    creating: { label: 'Pago pendiente', tone: 'warning', showAmount: true },
    pending: { label: 'Pago pendiente', tone: 'warning', showAmount: true },
    rejected: { label: 'Pago rechazado', tone: 'muted', showAmount: false },
    cancelled: { label: 'Pago cancelado', tone: 'muted', showAmount: false },
    error: { label: 'Error al iniciar el pago', tone: 'muted', showAmount: false },
};

/** Badge financiero del turno, o null si nunca hubo intento de pago. */
export function paymentBadge(summary: AppointmentPaymentSummary | null | undefined): PaymentBadge | null {
    if (!summary) return null;
    // `requires_review` manda aunque el status llegara con otro valor.
    if (summary.requires_review) return PAYMENT_BADGES.requires_review;
    return PAYMENT_BADGES[summary.status] ?? null;
}

const REVIEW_REASON_COPY: Record<AppointmentPaymentReviewReason, string> = {
    approved_after_expiry:
        'El pago se acreditó después de que venció la reserva, así que el turno no se confirmó automáticamente.',
    approval_time_unknown:
        'No pudimos verificar cuándo se aprobó el pago, así que el turno no se confirmó automáticamente.',
    slot_conflict: 'El pago se acreditó, pero el horario ya estaba ocupado por otro turno.',
    appointment_already_confirmed:
        'El pago se acreditó, pero el turno ya estaba confirmado por otra vía (posible pago duplicado).',
    appointment_not_payable: 'El pago se acreditó, pero el turno ya estaba cancelado o finalizado.',
};

const REVIEW_REASON_FALLBACK = 'El pago se acreditó pero requiere revisión manual.';

/** Explicación operativa de un pago en revisión (nunca el código técnico). */
export function reviewReasonCopy(reason: AppointmentPaymentReviewReason | string | null | undefined): string {
    if (reason && reason in REVIEW_REASON_COPY) {
        return REVIEW_REASON_COPY[reason as AppointmentPaymentReviewReason];
    }
    return REVIEW_REASON_FALLBACK;
}
