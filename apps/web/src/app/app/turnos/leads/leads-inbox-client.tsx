"use client";

import type { Route } from 'next';
import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import { useLeads } from '@/features/leads/hooks';
import {
    LEAD_OUTCOME_LABELS,
    LEAD_SOURCE_LABELS,
    LEAD_STATUS_LABELS,
    LEADS_UNASSIGNED,
    LEADS_UNLINKED,
    type ConversationControlState,
    type LeadFilters,
    type LeadListItem,
    type LeadOutcome,
    type LeadSource,
    type LeadStatus,
} from '@/features/leads/types';
import { ApiError } from '@/lib/api/client';
import { dateTimeInTimeZone, resolveBusinessTimeZone } from '@/lib/business-time';
import { cn } from '@/lib/utils';

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
};

const EMPTY_FILTERS: FilterState = {
    status: '',
    source: '',
    outcome: '',
    urgency: '',
    needsAttention: '',
    assignedTo: '',
    customer: '',
};

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
        q: q || undefined,
        limit: LEADS_PAGE_SIZE,
        offset,
    };
}

type LeadsInboxClientProps = {
    currentUserId: number | null;
    businessTimeZone: string | null;
};

export function LeadsInboxClient({ currentUserId, businessTimeZone }: LeadsInboxClientProps) {
    const timeZone = resolveBusinessTimeZone(businessTimeZone);
    const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
    const [search, setSearch] = useState('');
    const [debouncedSearch, setDebouncedSearch] = useState('');
    const [offset, setOffset] = useState(0);

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
                        options={[['true', 'Atención pendiente'], ['false', 'Sin atención pendiente']]}
                    />
                    <FilterSelect
                        label="Urgencia"
                        value={filters.urgency}
                        onChange={(value) => updateFilter('urgency', value as BoolFilter)}
                        options={[['true', 'Urgentes'], ['false', 'No urgentes']]}
                    />
                    <FilterSelect
                        label="Estado"
                        value={filters.status}
                        onChange={(value) => updateFilter('status', value as FilterState['status'])}
                        options={Object.entries(LEAD_STATUS_LABELS)}
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
                    <FilterSelect
                        label="Canal"
                        value={filters.source}
                        onChange={(value) => updateFilter('source', value as FilterState['source'])}
                        options={Object.entries(LEAD_SOURCE_LABELS)}
                    />
                </div>
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
                                <LeadRow key={lead.id} lead={lead} timeZone={timeZone} />
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

const STATUS_BADGE: Record<LeadStatus, string> = {
    new: 'bg-sky-100 text-sky-700',
    in_progress: 'bg-violet-100 text-violet-700',
    closed: 'bg-slate-200 text-slate-600',
};

/**
 * Control de la conversación (MIRUBRO TAKEOVER 05B): info secundaria, después
 * de atención/urgencia/estado. `active` (modo del bot habilitado, no una
 * confirmación de que esté respondiendo bien) no lleva badge.
 */
const CONVERSATION_BADGE: Partial<Record<ConversationControlState, { label: string; title: string; className: string }>> = {
    taken: { label: 'Humano', title: 'Conversación tomada: el bot está pausado', className: 'bg-indigo-50 text-indigo-700' },
    takeover_pending: { label: 'Procesando', title: 'Tomando la conversación', className: 'bg-slate-100 text-slate-600' },
    release_pending: { label: 'Procesando', title: 'Reanudando el bot', className: 'bg-slate-100 text-slate-600' },
    error: { label: 'Error de control', title: 'No se pudo cambiar el control del bot', className: 'bg-rose-50 text-rose-700' },
};

function LeadRow({ lead, timeZone }: { lead: LeadListItem; timeZone: string }) {
    const agent = lead.agent;
    const closed = lead.status === 'closed';
    const reason = agent?.reason || agent?.summary;
    const name = leadDisplayName(lead);
    const phone = agent?.phone_e164 && agent.phone_e164 !== name ? agent.phone_e164 : null;
    const conversation = lead.conversation_state ? CONVERSATION_BADGE[lead.conversation_state] : undefined;

    return (
        <li>
            <Link
                href={`/app/turnos/leads/${lead.id}` as Route}
                data-testid="lead-row"
                data-attention={lead.needs_attention ? 'pending' : undefined}
                className={cn(
                    'flex flex-col gap-3 border-l-4 px-3 py-3 transition hover:bg-slate-50 md:flex-row md:items-start md:justify-between',
                    lead.needs_attention ? 'border-amber-400 bg-amber-50/60' : 'border-transparent',
                    closed && 'opacity-70',
                )}
            >
                <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate font-semibold text-slate-900">{name}</p>
                        {lead.needs_attention ? (
                            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800">
                                Atención pendiente
                            </span>
                        ) : null}
                        {agent?.urgency ? (
                            <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-semibold text-rose-700">Urgente</span>
                        ) : null}
                        <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-semibold', STATUS_BADGE[lead.status])}>
                            {LEAD_STATUS_LABELS[lead.status]}
                            {closed && lead.outcome ? ` · ${LEAD_OUTCOME_LABELS[lead.outcome]}` : ''}
                        </span>
                        {conversation ? (
                            <span
                                data-testid="lead-conversation-badge"
                                title={conversation.title}
                                className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', conversation.className)}
                            >
                                {conversation.label}
                            </span>
                        ) : null}
                    </div>
                    <p className="text-xs text-slate-500">
                        {phone ? `${phone} · ` : ''}
                        {LEAD_SOURCE_LABELS[lead.source] ?? lead.source}
                    </p>
                    {reason ? <p className="line-clamp-2 text-sm text-slate-600">{reason}</p> : null}
                    <p className="text-xs text-slate-500">
                        <span className={lead.assigned_to ? 'text-slate-700' : 'italic'}>
                            {lead.assigned_to ? `Asignado a ${lead.assigned_to.display_name}` : 'Sin asignar'}
                        </span>
                        {lead.customer ? <span> · Cliente: {lead.customer.display_name}</span> : null}
                    </p>
                </div>
                <dl className="grid shrink-0 grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-500 md:block md:text-right">
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
            </Link>
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
