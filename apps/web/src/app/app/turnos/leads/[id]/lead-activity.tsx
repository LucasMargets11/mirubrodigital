"use client";

import { APPOINTMENT_STATUS_LABELS, type AppointmentStatus } from '@/features/appointments/types';
import type { LeadActivity, LeadActivityRef } from '@/features/leads/types';
import { dateTimeInTimeZone } from '@/lib/business-time';

import { formatAppointmentWhen } from '../../../clientes/[id]/customer-upcoming-appointments';

function asRecord(ref: LeadActivityRef | null | undefined): Record<string, unknown> | null {
    return ref && typeof ref === 'object' ? (ref as Record<string, unknown>) : null;
}

/** Etiqueta de un `{value, label}` (estado/resultado). */
function choiceLabel(ref: unknown): string | null {
    const record = ref && typeof ref === 'object' ? (ref as Record<string, unknown>) : null;
    return typeof record?.label === 'string' ? record.label : null;
}

function personLabel(ref: LeadActivityRef | null): string {
    const name = asRecord(ref)?.display_name;
    return typeof name === 'string' && name ? name : 'una persona que ya no está en el equipo';
}

function customerLabel(ref: LeadActivityRef | null): string {
    const name = asRecord(ref)?.display_name;
    return typeof name === 'string' && name ? name : 'un cliente eliminado';
}

function appointmentLabel(ref: LeadActivityRef | null, timeZone: string): string {
    const record = asRecord(ref);
    const startAt = record?.start_at;
    if (typeof startAt !== 'string' || !startAt) return 'un turno eliminado';
    const service = typeof record?.service_name === 'string' && record.service_name ? ` (${record.service_name})` : '';
    return `el turno del ${formatAppointmentWhen(startAt, timeZone)}${service}`;
}

// `takeover_applied`/`release_applied`/`*_failed` are the agent's OWN async
// confirmation (it ack's the command some time after a human requested it,
// see apps.leads.services.takeover._record_activity): the backend never
// attaches an actor to these, by design, not because a user got deleted.
// Only `*_requested` (and every other kind) are human-authored and a null
// actor there really does mean the user no longer exists.
const SYSTEM_CONFIRMED_KINDS = new Set<string>([
    'takeover_applied',
    'takeover_failed',
    'release_applied',
    'release_failed',
]);

/**
 * Texto humano de un evento del historial (LEADS 04B.4). Nunca muestra los
 * ids crudos de `previous`/`new` ni el JSON de `metadata`: si una referencia
 * ya no existe se nombra genéricamente. Un `kind` desconocido cae en
 * `kind_display` del backend.
 */
export function describeLeadActivity(activity: LeadActivity, timeZone: string): string {
    const { previous, new: next } = activity;
    switch (activity.kind) {
        case 'status_changed':
            return `Cambió el estado de ${choiceLabel(previous) ?? '—'} a ${choiceLabel(next) ?? '—'}`;
        case 'closed': {
            const outcome = choiceLabel(activity.metadata?.outcome);
            return outcome ? `Cerró el lead · Resultado: ${outcome}` : 'Cerró el lead';
        }
        case 'outcome_changed':
            return `Cambió el resultado de ${choiceLabel(previous) ?? '—'} a ${choiceLabel(next) ?? '—'}`;
        case 'assigned':
            return `Asignó el lead a ${personLabel(next)}`;
        case 'reassigned':
            return `Reasignó el lead de ${personLabel(previous)} a ${personLabel(next)}`;
        case 'unassigned':
            return `Quitó la asignación a ${personLabel(previous)}`;
        case 'customer_linked':
            return `Vinculó al cliente ${customerLabel(next)}`;
        case 'customer_changed':
            return `Cambió el cliente de ${customerLabel(previous)} a ${customerLabel(next)}`;
        case 'customer_unlinked':
            return `Desvinculó al cliente ${customerLabel(previous)}`;
        case 'appointment_linked':
            return `Vinculó ${appointmentLabel(next, timeZone)}`;
        case 'appointment_changed':
            return `Cambió el turno vinculado: antes ${appointmentLabel(previous, timeZone)}, ahora ${appointmentLabel(next, timeZone)}`;
        case 'appointment_unlinked':
            return `Desvinculó ${appointmentLabel(previous, timeZone)}`;
        case 'attention_acknowledged':
            return 'Reconoció el pedido de atención';
        default:
            return activity.kind_display || 'Actualizó el lead';
    }
}

/** Estado del turno en un evento (solo vínculos), para un badge chico. */
function appointmentStatusOf(activity: LeadActivity): string | null {
    if (!activity.kind.startsWith('appointment_') || activity.kind === 'appointment_unlinked') return null;
    const status = asRecord(activity.new)?.status;
    return typeof status === 'string' ? APPOINTMENT_STATUS_LABELS[status as AppointmentStatus] ?? null : null;
}

/** Historial read-only del Lead, más reciente primero (orden del backend). */
export function LeadActivityTimeline({ activity, timeZone }: { activity: LeadActivity[]; timeZone: string }) {
    return (
        <section aria-label="Historial" className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Historial</h3>
            {activity.length === 0 ? (
                <p className="mt-3 text-sm text-slate-500">Todavía no hay cambios registrados en este lead.</p>
            ) : (
                <ol className="mt-3 space-y-3 border-l border-slate-200 pl-4">
                    {activity.map((event) => {
                        const appointmentStatus = appointmentStatusOf(event);
                        return (
                            <li key={event.id} data-testid="lead-activity" className="relative">
                                <span aria-hidden className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full bg-slate-300" />
                                <p className="text-sm text-slate-800">
                                    {describeLeadActivity(event, timeZone)}
                                    {appointmentStatus ? (
                                        <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                                            {appointmentStatus}
                                        </span>
                                    ) : null}
                                </p>
                                <p className="text-xs text-slate-400">
                                    {event.actor?.display_name ?? (SYSTEM_CONFIRMED_KINDS.has(event.kind) ? 'Confirmación automática del agente' : 'Usuario eliminado')} · {dateTimeInTimeZone(event.occurred_at, timeZone)}
                                </p>
                            </li>
                        );
                    })}
                </ol>
            )}
        </section>
    );
}
