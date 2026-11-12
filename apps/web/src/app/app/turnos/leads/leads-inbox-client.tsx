"use client";

import type { Route } from 'next';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';

import { useLeads } from '@/features/leads/hooks';
import {
    LEAD_OUTCOME_LABELS,
    LEAD_SOURCE_LABELS,
    LEAD_STATUS_LABELS,
    LEADS_UNASSIGNED,
    LEADS_UNLINKED,
    type ConversationControlState,
    type LeadAppointmentFilter,
    type LeadFilters,
    type LeadListAppointment,
    type LeadListItem,
    type LeadOutcome,
    type LeadSource,
    type LeadStatus,
} from '@/features/leads/types';
import { ApiError } from '@/lib/api/client';
import { dateTimeInTimeZone, resolveBusinessTimeZone } from '@/lib/business-time';
import { cn } from '@/lib/utils';

import { agendaHref, formatAppointmentWhen } from '../../clientes/[id]/customer-upcoming-appointments';

export const LEADS_PAGE_SIZE = 25;
const SEARCH_DEBOUNCE_MS = 300;
const ASSIGNED_TO_ME = 'me';

type BoolFilter = '' | 'true' | 'false';

/** Estado de los controles (strings de los <select>); se traduce 1:1 a parámetros del backend. */
type FilterState = {
    status: '' | LeadStatus;
    source: '' | LeadSource;
    outcome: '' | LeadOutcome;
    urgency: BoolFilter;
    needsAttention: BoolFilter;
    assignedTo: '' | typeof ASSIGNED_TO_ME | typeof LEADS_UNASSIGNED;
    customer: '' | typeof LEADS_UNLINKED;
    appointment: '' | LeadAppointmentFilter;
};

const EMPTY_FILTERS: FilterState = {
    status: '',
    source: '',
    outcome: '',
    urgency: '',
    needsAttention: '',
    assignedTo: '',
    customer: '',
    appointment: '',
};

/** Filtros fuera de la superficie principal (se abren con "Más filtros"). */
const SECONDARY_FILTER_KEYS = ['status', 'urgency', 'customer', 'outcome'] as const;

function toBool(value: BoolFilter): boolean | undefined {
    return value === '' ? undefined : value === 'true';
}

export function buildApiFilters(
    filters: FilterState,
    q: string,
    offset: number,
    currentUserId: number | null,
): LeadFilters {
    let assignedTo: string | undefined;
    if (filters.assignedTo === LEADS_UNASSIGNED) {
        assignedTo = LEADS_UNASSIGNED;
    } else if (filters.assignedTo === ASSIGNED_TO_ME && currentUserId != null) {
        assignedTo = String(currentUserId);
    }
    return {
        status: filters.status || undefined,
        source: filters.source || undefined,
        outcome: filters.outcome || undefined,
        urgency: toBool(filters.urgency),
        needsAttention: toBool(filters.needsAttention),
        assignedTo,
        customer: filters.customer || undefined,
        appointment: filters.appointment || undefined,
        q: q || undefined,
        limit: LEADS_PAGE_SIZE,
        offset,
    };
}

type LeadsInboxClientProps = {
    currentUserId: number | null;
    businessTimeZone: string | null;
    /** `manage_leads`: habilita "Gestionar turno" (junto con `manage_appointments`). */
    canManage?: boolean;
    canManageAppointments?: boolean;
    /** `view_appointments`: "Ver turno" abre la agenda; sin él, el turno dentro del Lead. */
    canViewAppointments?: boolean;
};

export function LeadsInboxClient({
    currentUserId,
    businessTimeZone,
    canManage = false,
    canManageAppointments = false,
    canViewAppointments = false,
}: LeadsInboxClientProps) {
    const timeZone = resolveBusinessTimeZone(businessTimeZone);
    const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
    const [search, setSearch] = useState('');
    const [debouncedSearch, setDebouncedSearch] = useState('');
    const [offset, setOffset] = useState(0);
    const [showMoreFilters, setShowMoreFilters] = useState(false);
    const ctaContext: LeadCtaContext = { canManage, canManageAppointments, canViewAppointments, timeZone };

    useEffect(() => {
        const timeout = setTimeout(() => {
            setDebouncedSearch(search.trim());
            setOffset(0);
        }, SEARCH_DEBOUNCE_MS);
        return () => clearTimeout(timeout);
    }, [search]);

    const apiFilters = useMemo(
        () => buildApiFilters(filters, debouncedSearch, offset, currentUserId),
        [filters, debouncedSearch, offset, currentUserId],
    );
    const leadsQuery = useLeads(apiFilters);
    const leads = leadsQuery.data?.results ?? [];
    const count = leadsQuery.data?.count ?? 0;
    const hasActiveFilters = search.trim() !== '' || Object.values(filters).some((value) => value !== '');
    const activeSecondaryFilters = SECONDARY_FILTER_KEYS.filter((key) => filters[key] !== '').length;

    const updateFilter = <K extends keyof FilterState>(key: K, value: FilterState[K]) => {
        setFilters((current) => ({ ...current, [key]: value }));
        setOffset(0);
    };

    const clearFilters = () => {
        setFilters(EMPTY_FILTERS);
        setSearch('');
        setDebouncedSearch('');
        setOffset(0);
    };

    return (
        <section className="space-y-4">
            <header className="flex flex-col gap-3 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm md:flex-row md:items-center md:justify-between">
                <div>
                    <h2 className="text-2xl font-semibold text-slate-900">Leads</h2>
                    <p className="text-sm text-slate-500">
                        Consultas que llegaron por el agente de WhatsApp. Primero las que esperan atención.
                    </p>
                </div>
                <button
                    type="button"
                    onClick={() => void leadsQuery.refetch()}
                    disabled={leadsQuery.isFetching}
                    className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:border-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
                >
                    {leadsQuery.isFetching && !leadsQuery.isLoading ? 'Actualizando…' : 'Actualizar'}
                </button>
            </header>

            <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <input
                        type="search"
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                        placeholder="Buscar por nombre, teléfono o motivo"
                        aria-label="Buscar leads"
                        className="rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none sm:col-span-2"
                    />
                    <FilterSelect
                        label="Atención"
                        value={filters.needsAttention}
                        onChange={(value) => updateFilter('needsAttention', value as BoolFilter)}
                        options={[['true', 'Necesita revisión'], ['false', 'Sin revisión pendiente']]}
                    />
                    <FilterSelect
                        label="Turno"
                        value={filters.appointment}
                        onChange={(value) => updateFilter('appointment', value as FilterState['appointment'])}
                        options={[['with', 'Con turno vinculado'], ['without', 'Sin turno vinculado']]}
                    />
                    <FilterSelect
                        label="Asignación"
                        value={filters.assignedTo}
                        onChange={(value) => updateFilter('assignedTo', value as FilterState['assignedTo'])}
                        options={[
                            ...(currentUserId != null ? [[ASSIGNED_TO_ME, 'Asignados a mí'] as [string, string]] : []),
                            [LEADS_UNASSIGNED, 'Sin asignar'],
                        ]}
                    />
                    <div className="flex items-end">
                        <button
                            type="button"
                            aria-expanded={showMoreFilters}
                            aria-controls="leads-more-filters"
                            onClick={() => setShowMoreFilters((current) => !current)}
                            className="w-full rounded-2xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:border-slate-300"
                        >
                            {showMoreFilters ? 'Menos filtros' : 'Más filtros'}
                            {activeSecondaryFilters > 0 ? ` (${activeSecondaryFilters})` : ''}
                        </button>
                    </div>
                </div>
                {showMoreFilters ? (
                    <div id="leads-more-filters" className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                        <FilterSelect
                            label="Estado"
                            value={filters.status}
                            onChange={(value) => updateFilter('status', value as FilterState['status'])}
                            options={Object.entries(LEAD_STATUS_LABELS)}
                        />
                        <FilterSelect
                            label="Urgencia"
                            value={filters.urgency}
                            onChange={(value) => updateFilter('urgency', value as BoolFilter)}
                            options={[['true', 'Urgentes'], ['false', 'No urgentes']]}
                        />
                        <FilterSelect
                            label="Cliente"
                            value={filters.customer}
                            onChange={(value) => updateFilter('customer', value as FilterState['customer'])}
                            options={[[LEADS_UNLINKED, 'Sin cliente vinculado']]}
                        />
                        <FilterSelect
                            label="Resultado"
                            value={filters.outcome}
                            onChange={(value) => updateFilter('outcome', value as FilterState['outcome'])}
                            options={Object.entries(LEAD_OUTCOME_LABELS)}
                        />
                    </div>
                ) : null}
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs uppercase tracking-wide text-slate-400">
                        {leadsQuery.isLoading ? 'Cargando…' : `${count} ${count === 1 ? 'lead' : 'leads'}`}
                    </p>
                    {hasActiveFilters ? (
                        <button type="button" onClick={clearFilters} className="text-xs font-semibold text-slate-600 hover:text-slate-900">
                            Limpiar filtros
                        </button>
                    ) : null}
                </div>

                <div className="mt-4">
                    {leadsQuery.isLoading ? (
                        <p role="status" className="px-3 py-6 text-center text-sm text-slate-500">Cargando leads…</p>
                    ) : leadsQuery.isError ? (
                        <LeadsError error={leadsQuery.error} onRetry={() => void leadsQuery.refetch()} />
                    ) : leads.length === 0 ? (
                        <p className="px-3 py-6 text-center text-sm text-slate-500">
                            {hasActiveFilters
                                ? 'No hay leads que coincidan con los filtros.'
                                : 'Todavía no llegaron consultas del agente de WhatsApp.'}
                        </p>
                    ) : (
                        <ul aria-label="Bandeja de leads" className="divide-y divide-slate-100">
                            {leads.map((lead) => (
                                <LeadRow
                                    key={lead.id}
                                    lead={lead}
                                    timeZone={timeZone}
                                    currentUserId={currentUserId}
                                    ctaContext={ctaContext}
                                />
                            ))}
                        </ul>
                    )}
                </div>

                {!leadsQuery.isLoading && !leadsQuery.isError && count > LEADS_PAGE_SIZE ? (
                    <LeadsPagination
                        count={count}
                        offset={offset}
                        onChange={setOffset}
                        disabled={leadsQuery.isFetching}
                    />
                ) : null}
            </div>
        </section>
    );
}

type FilterSelectProps = {
    label: string;
    value: string;
    onChange: (value: string) => void;
    options: Array<[string, string]>;
};

function FilterSelect({ label, value, onChange, options }: FilterSelectProps) {
    return (
        <label className="flex flex-col gap-1 text-xs font-semibold text-slate-500">
            {label}
            <select
                value={value}
                onChange={(event) => onChange(event.target.value)}
                className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm font-normal text-slate-700 focus:border-slate-900 focus:outline-none"
            >
                <option value="">Todos</option>
                {options.map(([optionValue, optionLabel]) => (
                    <option key={optionValue} value={optionValue}>{optionLabel}</option>
                ))}
            </select>
        </label>
    );
}

export function leadDisplayName(lead: LeadListItem): string {
    return (
        lead.agent?.patient_name
        || lead.agent?.whatsapp_profile_name
        || lead.customer?.display_name
        || lead.agent?.phone_e164
        || 'Sin nombre'
    );
}

/**
 * Control de la conversación (MIRUBRO TAKEOVER 05B): concepto separado de la
 * atención. `active` (bot habilitado) no lleva indicador.
 */
const CONVERSATION_PENDING_LABEL: Partial<Record<ConversationControlState, string>> = {
    takeover_pending: 'Tomando la conversación…',
    release_pending: 'Reactivando el bot…',
    error: 'Error de control del bot',
};

function conversationState(lead: LeadListItem): ConversationControlState | null {
    return lead.conversation_control?.state ?? lead.conversation_state ?? null;
}

/** "Tomada por X" / "Tomada por vos"; nunca asume que el asignado es quien la tomó. */
export function conversationLabel(lead: LeadListItem, currentUserId: number | null): string | null {
    const state = conversationState(lead);
    // Derivación: el bot ya no responde y nadie tomó el chat todavía
    if (state === 'active' && lead.conversation_control?.handoff_pending) {
        return 'Pendiente de recepción · bot pausado';
    }
    if (state === 'taken') {
        const takenBy = lead.conversation_control?.taken_by;
        if (!takenBy) return 'Conversación tomada';
        return takenBy.id === currentUserId ? 'Tomada por vos' : `Tomada por ${takenBy.display_name}`;
    }
    return state ? CONVERSATION_PENDING_LABEL[state] ?? null : null;
}

/**
 * Etiqueta del turno vinculado. Solo presenta: no corrige estados persistidos
 * (un `confirmed` que ya terminó se muestra como pasado, sin marcarlo completado).
 */
export function appointmentLabel(appointment: LeadListAppointment): string {
    switch (appointment.status) {
        case 'confirmed':
            return appointment.is_past ? 'Turno pasado · figura confirmado' : 'Turno confirmado';
        case 'pending_payment':
            return 'Pendiente de pago';
        case 'expired':
            return 'Reserva vencida';
        case 'cancelled':
            return 'Turno cancelado';
        case 'completed':
            return 'Turno completado';
        case 'no_show':
            return 'No asistió';
        default:
            return 'Turno vinculado';
    }
}

const APPOINTMENT_TONE: Record<LeadListAppointment['status'], string> = {
    confirmed: 'text-emerald-700',
    pending_payment: 'text-amber-700',
    expired: 'text-slate-500',
    cancelled: 'text-rose-700',
    completed: 'text-slate-600',
    no_show: 'text-rose-700',
};

export type LeadCtaKind =
    | 'detail'
    | 'review_conversation'
    | 'view_conversation'
    | 'open_conversation'
    | 'attend'
    | 'view_appointment'
    | 'manage_appointment';

export type LeadCta = { kind: LeadCtaKind; label: string; href: string };

export type LeadCtaContext = {
    canManage: boolean;
    canManageAppointments: boolean;
    canViewAppointments: boolean;
    timeZone: string;
};

/**
 * CTA principal de la fila (SLICE 2). Todas navegan: ninguna reconoce la
 * atención, toma la conversación ni crea/modifica turnos.
 */
export function resolveLeadCta(lead: LeadListItem, context: LeadCtaContext): LeadCta {
    const detail = `/app/turnos/leads/${lead.id}`;
    const state = conversationState(lead);
    if (lead.status === 'closed') return { kind: 'detail', label: 'Ver detalle', href: detail };
    if (state === 'error') return { kind: 'review_conversation', label: 'Revisar conversación', href: detail };
    if (state === 'takeover_pending' || state === 'release_pending') {
        return { kind: 'view_conversation', label: 'Ver conversación', href: detail };
    }
    if (state === 'taken') return { kind: 'open_conversation', label: 'Abrir conversación', href: detail };
    if (lead.needs_attention) return { kind: 'attend', label: 'Atender', href: detail };
    if (lead.appointment) {
        return {
            kind: 'view_appointment',
            label: 'Ver turno',
            href: context.canViewAppointments ? agendaHref(lead.appointment, context.timeZone) : `${detail}#turno`,
        };
    }
    if (context.canManage && context.canManageAppointments) {
        return { kind: 'manage_appointment', label: 'Gestionar turno', href: `${detail}#turno` };
    }
    return { kind: 'detail', label: 'Ver detalle', href: detail };
}

const STATUS_BADGE: Record<LeadStatus, string> = {
    new: 'bg-sky-100 text-sky-700',
    in_progress: 'bg-violet-100 text-violet-700',
    closed: 'bg-slate-200 text-slate-600',
};

type LeadRowProps = {
    lead: LeadListItem;
    timeZone: string;
    currentUserId: number | null;
    ctaContext: LeadCtaContext;
};

function LeadRow({ lead, timeZone, currentUserId, ctaContext }: LeadRowProps) {
    const router = useRouter();
    const detailHref = `/app/turnos/leads/${lead.id}` as Route;
    const agent = lead.agent;
    const closed = lead.status === 'closed';
    const reason = agent?.reason || agent?.summary;
    const name = leadDisplayName(lead);
    const phone = agent?.phone_e164 && agent.phone_e164 !== name ? agent.phone_e164 : null;
    const conversation = conversationLabel(lead, currentUserId);
    const state = conversationState(lead);
    const cta = resolveLeadCta(lead, ctaContext);
    const appointment = lead.appointment;

    return (
        <li
            data-testid="lead-row"
            onClick={(event) => {
                if (event.target instanceof Element && event.target.closest('a, button, input, select, textarea, [role="button"]')) return;
                router.push(detailHref);
            }}
            data-attention={lead.needs_attention ? 'pending' : undefined}
            className={cn(
                'relative flex cursor-pointer flex-col gap-3 border-l-4 px-3 py-3 hover:bg-slate-50 md:flex-row md:items-start md:justify-between',
                lead.needs_attention ? 'border-amber-400 bg-amber-50/60' : 'border-transparent',
                closed && 'opacity-70',
            )}
        >
            <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                    <Link
                        href={`/app/turnos/leads/${lead.id}` as Route}
                        data-testid="lead-name"
                        onClick={(event) => event.stopPropagation()}
                        onKeyDown={(event) => {
                            if (event.key === ' ') {
                                event.preventDefault();
                                event.currentTarget.click();
                            }
                        }}
                        className="min-w-0 truncate font-semibold text-slate-900 after:absolute after:inset-0 after:content-[''] hover:underline focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-inset focus-visible:after:ring-slate-900"
                    >
                        {name}
                    </Link>
                    {lead.needs_attention ? (
                        <span
                            data-testid="lead-attention-badge"
                            className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800"
                        >
                            Necesita revisión
                        </span>
                    ) : null}
                    {agent?.urgency ? (
                        <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-semibold text-rose-700">Urgente</span>
                    ) : null}
                    <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-semibold', STATUS_BADGE[lead.status])}>
                        {LEAD_STATUS_LABELS[lead.status]}
                        {closed && lead.outcome ? ` · ${LEAD_OUTCOME_LABELS[lead.outcome]}` : ''}
                    </span>
                </div>
                <p className="text-xs text-slate-500">
                    {phone ? `${phone} · ` : ''}
                    {LEAD_SOURCE_LABELS[lead.source] ?? lead.source}
                </p>
                {reason || agent?.preferred_time ? (
                    <p data-testid="lead-intent" className="line-clamp-2 break-words text-sm text-slate-700">
                        {reason}
                        {reason && agent?.preferred_time ? ' · ' : ''}
                        {agent?.preferred_time ? (
                            <span className="text-slate-500">Prefiere {agent.preferred_time}</span>
                        ) : null}
                    </p>
                ) : null}
                <p
                    data-testid="lead-last-patient-message"
                    className={cn(
                        'line-clamp-2 break-words text-sm',
                        lead.last_patient_message_text ? 'text-slate-600' : 'italic text-slate-400',
                    )}
                >
                    {lead.last_patient_message_text
                        ? `“${lead.last_patient_message_text}”`
                        : 'Sin mensajes del paciente disponibles'}
                    {lead.last_patient_message_text && lead.last_patient_message_at ? (
                        <span className="not-italic text-xs text-slate-400">
                            {' '}· {dateTimeInTimeZone(lead.last_patient_message_at, timeZone)}
                        </span>
                    ) : null}
                </p>
                {conversation ? (
                    <p
                        data-testid="lead-conversation"
                        className={cn(
                            'text-xs font-medium',
                            state === 'error' ? 'text-rose-700' : state === 'taken' ? 'text-indigo-700' : 'text-slate-500',
                        )}
                    >
                        {conversation}
                    </p>
                ) : null}
                <p className="text-xs text-slate-500">
                    <span className={lead.assigned_to ? 'text-slate-700' : 'italic'}>
                        {lead.assigned_to ? `Asignado a ${lead.assigned_to.display_name}` : 'Sin asignar'}
                    </span>
                    {lead.customer ? <span> · Cliente: {lead.customer.display_name}</span> : null}
                </p>
            </div>
            <div className="flex shrink-0 flex-col gap-2 text-xs text-slate-500 md:w-64 md:items-end md:text-right">
                <div data-testid="lead-appointment-summary" className="space-y-0.5">
                    {appointment ? (
                        <>
                            <p className={cn('font-semibold', APPOINTMENT_TONE[appointment.status])}>
                                {appointmentLabel(appointment)}
                            </p>
                            <p className="text-slate-700">{formatAppointmentWhen(appointment.start_at, timeZone)}</p>
                            <p className="break-words">
                                {appointment.service_name}
                                {appointment.professional_name ? ` · ${appointment.professional_name}` : ''}
                            </p>
                        </>
                    ) : (
                        <p className="italic">Sin turno vinculado</p>
                    )}
                </div>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1 md:block">
                    {agent?.last_message_at ? (
                        <div>
                            <dt className="inline md:block">Último mensaje </dt>
                            <dd className="font-medium text-slate-700">{dateTimeInTimeZone(agent.last_message_at, timeZone)}</dd>
                        </div>
                    ) : null}
                    <div>
                        <dt className="inline md:block">Ingresó </dt>
                        <dd className="font-medium text-slate-700">{dateTimeInTimeZone(lead.created_at, timeZone)}</dd>
                    </div>
                </dl>
                <Link
                    href={cta.href as Route}
                    data-testid="lead-cta"
                    onClick={(event) => event.stopPropagation()}
                    data-cta={cta.kind}
                    aria-label={`${cta.label}: ${name}`}
                    className={cn(
                        'relative z-10 inline-flex justify-center rounded-full px-4 py-1.5 text-xs font-semibold focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900',
                        cta.kind === 'detail'
                            ? 'border border-slate-200 text-slate-700 hover:border-slate-300'
                            : 'bg-slate-900 text-white hover:bg-slate-700',
                    )}
                >
                    {cta.label}
                </Link>
            </div>
        </li>
    );
}

function LeadsError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
    const code = error instanceof ApiError
        ? (error.payload as { code?: string } | undefined)?.code
        : undefined;
    const message = code === 'plan_entitlement_required'
        ? 'Tu plan no incluye la bandeja de Leads.'
        : error instanceof ApiError && error.status === 403
            ? 'No tenés permiso para ver los leads.'
            : 'No pudimos cargar los leads.';
    return (
        <div role="alert" className="flex flex-col items-center gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-6 text-center text-sm text-rose-700">
            <p>{message}</p>
            <button
                type="button"
                onClick={onRetry}
                className="rounded-full border border-rose-200 bg-white px-4 py-1 text-xs font-semibold text-rose-700 hover:border-rose-300"
            >
                Reintentar
            </button>
        </div>
    );
}

type LeadsPaginationProps = {
    count: number;
    offset: number;
    onChange: (offset: number) => void;
    disabled?: boolean;
};

function LeadsPagination({ count, offset, onChange, disabled }: LeadsPaginationProps) {
    const totalPages = Math.max(1, Math.ceil(count / LEADS_PAGE_SIZE));
    const currentPage = Math.min(totalPages, Math.floor(offset / LEADS_PAGE_SIZE) + 1);
    return (
        <nav aria-label="Paginación" className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-700">
            <span>Página {currentPage} de {totalPages}</span>
            <div className="flex items-center gap-2">
                <button
                    type="button"
                    onClick={() => onChange(Math.max(0, offset - LEADS_PAGE_SIZE))}
                    disabled={offset === 0 || disabled}
                    className="rounded-full border border-slate-200 px-3 py-1 font-medium text-slate-600 hover:border-slate-300 disabled:cursor-not-allowed disabled:opacity-40"
                >
                    Anterior
                </button>
                <button
                    type="button"
                    onClick={() => onChange(offset + LEADS_PAGE_SIZE)}
                    disabled={offset + LEADS_PAGE_SIZE >= count || disabled}
                    className="rounded-full border border-slate-200 px-3 py-1 font-medium text-slate-600 hover:border-slate-300 disabled:cursor-not-allowed disabled:opacity-40"
                >
                    Siguiente
                </button>
            </div>
        </nav>
    );
}
