"use client";

import { useState } from 'react';

import { useCustomerDeliveries } from '@/features/customers/hooks';
import type { CustomerDelivery, CustomerDeliveryStatus } from '@/features/customers/types';
import { calendarParts, dateInTimeZone, timeInTimeZone } from '@/lib/business-time';

import { MONTHS } from './customer-upcoming-appointments';

export const DELIVERIES_PAGE_SIZE = 10;

const STATUS_STYLES: Record<CustomerDeliveryStatus, string> = {
    pending: 'bg-amber-50 text-amber-800',
    processing: 'bg-amber-50 text-amber-800',
    sent: 'bg-emerald-50 text-emerald-700',
    delivered: 'bg-emerald-50 text-emerald-700',
    failed: 'bg-rose-50 text-rose-700',
    skipped: 'bg-slate-100 text-slate-600',
    cancelled: 'bg-slate-100 text-slate-600',
};

/** Motivos de negocio (`skip_reason`): mismos códigos que `contact_preferences` + los del envío. */
const SKIP_REASON_LABELS: Record<string, string> = {
    do_not_contact: 'El cliente pidió no ser contactado',
    disabled: 'Canal no permitido',
    missing_phone: 'Sin teléfono',
    invalid_phone: 'Teléfono inválido',
    missing_email: 'Sin email',
    consent_missing: 'Consentimiento inválido',
    consent_destination_changed: 'El destino cambió desde la autorización',
    destination_changed: 'El destino cambió después de programarlo',
    customer_inactive: 'Cliente inactivo',
    channel_not_automatic: 'Canal no automático',
};

const FAILURE_LABELS: Record<string, string> = {
    fake_temporary_error: 'Error temporal del proveedor',
    fake_rejected: 'El proveedor rechazó el mensaje',
    provider_exception: 'Resultado desconocido del proveedor',
    outcome_unknown: 'Resultado desconocido del proveedor',
    ses_throttled: 'Error temporal del proveedor',
    ses_unavailable: 'Error temporal del proveedor',
    ses_network_error: 'Error temporal del proveedor',
    ses_identity_not_verified: 'Email no verificado en el proveedor',
    ses_message_rejected: 'El proveedor rechazó el mensaje',
    ses_invalid_destination: 'Email del cliente inválido',
    template_context_invalid: 'Faltan datos para armar el mensaje',
    template_unsupported: 'Mensaje no disponible por email',
};

export function skipReasonLabel(reason: string | null) {
    return (reason && SKIP_REASON_LABELS[reason]) || 'Omitido por las reglas de contacto';
}

export function failureLabel(code: string | null) {
    return (code && FAILURE_LABELS[code]) || 'Error del proveedor';
}

/** "03 oct · 14:02" en la zona del Business. */
function formatDeliveryWhen(iso: string, timeZone: string) {
    const { monthIndex, day } = calendarParts(dateInTimeZone(iso, timeZone));
    return `${String(day).padStart(2, '0')} ${MONTHS[monthIndex]} · ${timeInTimeZone(iso, timeZone)}`;
}

function occurredAt(delivery: CustomerDelivery) {
    return delivery.delivered_at ?? delivery.sent_at ?? delivery.failed_at ?? delivery.skipped_at ?? delivery.cancelled_at ?? delivery.created_at;
}

function detailLine(delivery: CustomerDelivery, timeZone: string): string | null {
    if (delivery.status === 'skipped') return skipReasonLabel(delivery.skip_reason);
    if (delivery.status === 'failed') {
        const label = failureLabel(delivery.failure_code);
        return delivery.next_retry_at ? `${label} · reintento ${formatDeliveryWhen(delivery.next_retry_at, timeZone)}` : label;
    }
    return null;
}

/**
 * Comunicaciones externas al cliente (CUSTOMER 07D.2): solo historial/
 * auditoría, sin acciones (no hay "Enviar"). Los Deliveries los crea y
 * ejecuta el backend; el destino llega ya enmascarado. Lectura con
 * `view_customers` (la misma que la ficha).
 */
export function CustomerDeliveries({ customerId, timeZone }: { customerId: string; timeZone: string }) {
    const [limit, setLimit] = useState(DELIVERIES_PAGE_SIZE);
    const query = useCustomerDeliveries(customerId, { limit });
    const deliveries = query.data?.results ?? [];
    const total = query.data?.count ?? 0;

    return (
        <section aria-label="Comunicaciones" className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Comunicaciones</h3>
            <p className="text-xs text-slate-400">Mensajes automáticos al cliente sobre sus turnos.</p>

            {query.isLoading ? (
                <p className="mt-3 text-sm text-slate-500">Cargando comunicaciones...</p>
            ) : query.isError ? (
                <p role="alert" className="mt-3 text-sm text-rose-600">
                    No pudimos cargar las comunicaciones.
                </p>
            ) : deliveries.length === 0 ? (
                <p className="mt-3 text-sm text-slate-500">Todavía no hubo comunicaciones automáticas con este cliente.</p>
            ) : (
                <ul className="mt-3 divide-y divide-slate-100">
                    {deliveries.map((delivery) => {
                        const detail = detailLine(delivery, timeZone);
                        return (
                            <li key={delivery.id} data-testid="customer-delivery" className="flex flex-col gap-1 py-3 sm:flex-row sm:items-start sm:justify-between">
                                <div className="min-w-0">
                                    <p className="text-sm font-semibold text-slate-800">
                                        {delivery.channel_display}
                                        {delivery.destination_masked ? (
                                            <span className="ml-2 font-normal text-slate-500">{delivery.destination_masked}</span>
                                        ) : null}
                                    </p>
                                    <p className="text-sm text-slate-600">{delivery.purpose_display}</p>
                                    {detail ? (
                                        <p className={`text-xs ${delivery.status === 'failed' ? 'text-rose-600' : 'text-slate-500'}`}>{detail}</p>
                                    ) : null}
                                    {delivery.provider_display ? (
                                        <p className="text-xs text-slate-400">Proveedor: {delivery.provider_display}</p>
                                    ) : null}
                                    {delivery.attempt_count > 0 ? (
                                        <p className="text-xs text-slate-400">
                                            Intentos: {delivery.attempt_count} de {delivery.max_attempts}
                                        </p>
                                    ) : null}
                                </div>
                                <div className="flex shrink-0 flex-wrap items-center gap-2 sm:flex-col sm:items-end">
                                    <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS_STYLES[delivery.status]}`}>
                                        {delivery.status_display}
                                    </span>
                                    {delivery.is_simulated ? (
                                        <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-500">Simulado</span>
                                    ) : null}
                                    <span className="text-xs text-slate-400">{formatDeliveryWhen(occurredAt(delivery), timeZone)}</span>
                                </div>
                            </li>
                        );
                    })}
                </ul>
            )}

            {deliveries.length < total ? (
                <button
                    type="button"
                    onClick={() => setLimit((current) => current + DELIVERIES_PAGE_SIZE)}
                    className="mt-2 min-h-11 text-sm font-semibold text-slate-500 hover:text-slate-900 sm:min-h-0"
                >
                    Ver más comunicaciones
                </button>
            ) : null}
        </section>
    );
}
