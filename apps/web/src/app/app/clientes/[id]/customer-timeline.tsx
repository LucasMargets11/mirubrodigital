"use client";

import type { Route } from 'next';
import Link from 'next/link';
import { useState } from 'react';

import { AppointmentPaymentBadge, AppointmentStatusBadge, isInactiveStatus } from '@/app/app/turnos/turnos/appointment-status';
import type { OrderPaymentStatus, OrderStatus, QuoteStatus, SaleStatus } from '@/features/gestion/types';
import { useCustomerTimeline } from '@/features/customers/hooks';
import type { CustomerTimelineEvent, CustomerTimelineType } from '@/features/customers/types';
import { ApiError } from '@/lib/api/client';
import { calendarParts, dateInTimeZone, timeInTimeZone } from '@/lib/business-time';
import { formatCurrencySmart } from '@/lib/format';

import { formatAppointmentWhen, MONTHS } from './customer-upcoming-appointments';

export const TIMELINE_PAGE_SIZE = 20;

const TYPE_LABELS: Record<CustomerTimelineType, string> = {
    appointment: 'Turno',
    sale: 'Venta',
    quote: 'Presupuesto',
    order: 'Pedido',
};

const TYPE_FILTER_LABELS: Record<CustomerTimelineType, string> = {
    appointment: 'Turnos',
    sale: 'Ventas',
    quote: 'Presupuestos',
    order: 'Pedidos',
};

const TYPE_STYLES: Record<CustomerTimelineType, string> = {
    appointment: 'bg-sky-100 text-sky-700',
    sale: 'bg-emerald-100 text-emerald-700',
    quote: 'bg-amber-100 text-amber-700',
    order: 'bg-indigo-100 text-indigo-700',
};

const LINK_LABELS: Record<CustomerTimelineType, string> = {
    appointment: 'Ver en agenda',
    sale: 'Ver venta',
    quote: 'Ver presupuesto',
    order: 'Ver pedido',
};

const SALE_STATUS_STYLES: Record<SaleStatus, string> = {
    completed: 'bg-emerald-100 text-emerald-700',
    cancelled: 'bg-rose-100 text-rose-700',
};

const QUOTE_STATUS_STYLES: Record<QuoteStatus, string> = {
    draft: 'bg-slate-100 text-slate-700',
    sent: 'bg-blue-100 text-blue-700',
    accepted: 'bg-emerald-100 text-emerald-700',
    rejected: 'bg-rose-100 text-rose-700',
    expired: 'bg-amber-100 text-amber-700',
    converted: 'bg-violet-100 text-violet-700',
};

// Mismos colores que el listado de pedidos (`gestion/ventas/pedidos`).
const ORDER_STATUS_STYLES: Record<OrderStatus, string> = {
    draft: 'bg-slate-100 text-slate-700',
    pending_confirmation: 'bg-amber-100 text-amber-700',
    confirmed: 'bg-blue-100 text-blue-700',
    in_preparation: 'bg-indigo-100 text-indigo-700',
    ready_for_delivery: 'bg-purple-100 text-purple-700',
    delivered: 'bg-emerald-100 text-emerald-700',
    cancelled: 'bg-rose-100 text-rose-700',
};

const ORDER_PAYMENT_STYLES: Record<OrderPaymentStatus, string> = {
    pending: 'text-rose-600',
    partial: 'text-amber-600',
    paid: 'text-emerald-600',
};

/** "02 OCT 2026" para el día (en la zona del Business) de un instante. */
export function formatTimelineDay(day: string) {
    const { year, monthIndex, day: dayOfMonth } = calendarParts(day);
    return `${String(dayOfMonth).padStart(2, '0')} ${MONTHS[monthIndex].toUpperCase()} ${year}`;
}

/** Agrupa eventos consecutivos por día local; el orden lo define el backend. */
function groupByDay(events: CustomerTimelineEvent[], timeZone: string) {
    const groups: Array<{ day: string; events: CustomerTimelineEvent[] }> = [];
    for (const event of events) {
        const day = dateInTimeZone(event.occurred_at, timeZone);
        const last = groups[groups.length - 1];
        if (last && last.day === day) {
            last.events.push(event);
        } else {
            groups.push({ day, events: [event] });
        }
    }
    return groups;
}

/**
 * Historial unificado del cliente (CUSTOMER 04A/04B): Turnos + Ventas +
 * Presupuestos + Pedidos desde `GET /customers/{id}/timeline/`. El backend decide qué
 * fuentes entran (módulos del Business + permisos por fuente) y el orden
 * (`occurred_at` desc); acá solo se agrupa por día y se pagina por offset.
 * Si ninguna fuente es visible (403) la sección no se muestra.
 */
export function CustomerTimeline({ customerId, timeZone }: { customerId: string; timeZone: string }) {
    const [offset, setOffset] = useState(0);
    const [filter, setFilter] = useState<CustomerTimelineType | null>(null);

    const query = useCustomerTimeline(customerId, {
        ...(filter ? { types: [filter] } : {}),
        limit: TIMELINE_PAGE_SIZE,
        offset,
    });
    // Las fuentes disponibles se recuerdan de la vista sin filtro para no
    // perder los chips al filtrar.
    const [availableTypes, setAvailableTypes] = useState<CustomerTimelineType[] | null>(null);
    const responseTypes = query.data?.types;
    if (!filter && responseTypes && responseTypes.join() !== (availableTypes ?? []).join()) {
        setAvailableTypes(responseTypes);
    }

    if (query.isError && query.error instanceof ApiError && query.error.status === 403) {
        return null;
    }

    const events = query.data?.results ?? [];
    const count = query.data?.count ?? 0;
    const types = availableTypes ?? responseTypes ?? [];

    const selectFilter = (next: CustomerTimelineType | null) => {
        setFilter(next);
        setOffset(0);
    };

    let body;
    if (query.isLoading) {
        body = <p className="text-sm text-slate-500">Cargando actividad...</p>;
    } else if (query.isError) {
        body = <p className="text-sm text-rose-600">No pudimos cargar la actividad del cliente.</p>;
    } else if (count === 0) {
        body = <p className="text-sm text-slate-500">No hay actividad registrada para este cliente.</p>;
    } else {
        const pageEnd = Math.min(offset + events.length, count);
        body = (
            <div className="space-y-4">
                {groupByDay(events, timeZone).map((group) => (
                    <section key={group.day} aria-label={formatTimelineDay(group.day)}>
                        <h4 className="text-xs font-semibold tracking-wide text-slate-400">{formatTimelineDay(group.day)}</h4>
                        <ul className="mt-2 divide-y divide-slate-100 rounded-2xl border border-slate-100">
                            {group.events.map((event) => (
                                <TimelineRow key={event.id} event={event} timeZone={timeZone} />
                            ))}
                        </ul>
                    </section>
                ))}
                {count > TIMELINE_PAGE_SIZE ? (
                    <div className="flex items-center justify-between gap-3 text-xs text-slate-500">
                        <span>
                            {offset + 1}–{pageEnd} de {count}
                        </span>
                        <div className="flex gap-2">
                            <button
                                type="button"
                                disabled={offset === 0}
                                onClick={() => setOffset((o) => Math.max(0, o - TIMELINE_PAGE_SIZE))}
                                className="rounded-full border border-slate-200 px-3 py-1 font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                                Más recientes
                            </button>
                            <button
                                type="button"
                                disabled={pageEnd >= count}
                                onClick={() => setOffset((o) => o + TIMELINE_PAGE_SIZE)}
                                className="rounded-full border border-slate-200 px-3 py-1 font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                                Más antiguos
                            </button>
                        </div>
                    </div>
                ) : null}
            </div>
        );
    }

    return (
        <section aria-label="Historial" className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Historial</h3>
                {/* Filtros solo si hay más de una fuente visible: nunca chips de módulos ausentes. */}
                {types.length > 1 ? (
                    <div role="group" aria-label="Filtrar historial" className="flex flex-wrap gap-1.5">
                        {[null, ...types].map((type) => {
                            const active = filter === type;
                            return (
                                <button
                                    key={type ?? 'all'}
                                    type="button"
                                    aria-pressed={active}
                                    onClick={() => selectFilter(type)}
                                    className={`rounded-full px-3 py-1 text-xs font-semibold ${
                                        active ? 'bg-slate-900 text-white' : 'border border-slate-200 text-slate-600 hover:text-slate-900'
                                    }`}
                                >
                                    {type ? TYPE_FILTER_LABELS[type] : 'Todo'}
                                </button>
                            );
                        })}
                    </div>
                ) : null}
            </div>
            {body}
        </section>
    );
}

function StatusBadge({ event }: { event: CustomerTimelineEvent }) {
    if (event.type === 'appointment') {
        return (
            <AppointmentStatusBadge
                appointment={{ effective_status: event.status, effective_status_display: event.status_display }}
            />
        );
    }
    let style: string | undefined;
    switch (event.type) {
        case 'sale':
            style = SALE_STATUS_STYLES[event.status];
            break;
        case 'quote':
            style = QUOTE_STATUS_STYLES[event.status];
            break;
        case 'order':
            style = ORDER_STATUS_STYLES[event.status];
            break;
    }
    return (
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${style ?? 'bg-slate-100 text-slate-700'}`}>
            {event.status_display}
        </span>
    );
}

function eventDetail(event: CustomerTimelineEvent): string | null {
    const parts: string[] = [];
    if (event.subtitle) parts.push(event.subtitle);
    if (event.type !== 'appointment' && event.metadata.items_count !== null) {
        parts.push(`${event.metadata.items_count} ${event.metadata.items_count === 1 ? 'ítem' : 'ítems'}`);
    }
    if (event.type === 'sale' && event.metadata.invoice) {
        const { full_number, status, status_display } = event.metadata.invoice;
        parts.push(`Factura ${full_number}${status === 'voided' ? ` (${status_display.toLowerCase()})` : ''}`);
    }
    return parts.length > 0 ? parts.join(' · ') : null;
}

function isInactiveEvent(event: CustomerTimelineEvent): boolean {
    switch (event.type) {
        case 'appointment':
            return isInactiveStatus(event.status);
        case 'sale':
        case 'order':
            return event.status === 'cancelled';
        case 'quote':
            return false;
    }
}

function TimelineRow({ event, timeZone }: { event: CustomerTimelineEvent; timeZone: string }) {
    const detail = eventDetail(event);
    const inactive = isInactiveEvent(event);
    return (
        <li
            data-testid="customer-timeline-event"
            data-type={event.type}
            className={`flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between ${inactive ? 'opacity-70' : ''}`}
        >
            <div className="min-w-0 space-y-0.5">
                <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ${TYPE_STYLES[event.type]}`}>
                        {TYPE_LABELS[event.type]}
                    </span>
                    <span className="text-xs text-slate-500">{timeInTimeZone(event.occurred_at, timeZone)}</span>
                </div>
                <p className="text-sm font-semibold text-slate-900">{event.title}</p>
                {detail ? <p className="text-sm text-slate-600">{detail}</p> : null}
                {/* CUSTOMER 04A.1: un cancelado/vencido se fecha por cuándo pasó; se aclara para cuándo era el turno. */}
                {event.type === 'appointment' && event.metadata.start_at !== event.occurred_at ? (
                    <p className="text-xs text-slate-500">Turno del {formatAppointmentWhen(event.metadata.start_at, timeZone)}</p>
                ) : null}
                <div className="flex flex-wrap items-center gap-1.5 pt-1">
                    <StatusBadge event={event} />
                    {event.type === 'appointment' ? <AppointmentPaymentBadge appointment={event.metadata} /> : null}
                    {event.type === 'order' && event.status !== 'cancelled' ? (
                        <span className={`text-[11px] font-semibold ${ORDER_PAYMENT_STYLES[event.metadata.payment_status]}`}>
                            Pago {event.metadata.payment_status_display.toLowerCase()}
                        </span>
                    ) : null}
                </div>
            </div>
            <div className="flex shrink-0 items-center gap-4 sm:flex-col sm:items-end sm:gap-1">
                {event.amount !== null ? (
                    <span className="text-sm font-semibold text-slate-700">
                        {formatCurrencySmart(event.amount)}
                        {event.currency && event.currency !== 'ARS' ? ` ${event.currency}` : ''}
                    </span>
                ) : null}
                {event.href ? (
                    <Link href={event.href as Route} className="text-xs font-semibold text-slate-500 hover:text-slate-900">
                        {LINK_LABELS[event.type]}
                    </Link>
                ) : null}
            </div>
        </li>
    );
}
