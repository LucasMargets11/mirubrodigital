"use client";

import type { Route } from 'next';
import Link from 'next/link';
import { useState, type ReactNode } from 'react';

import { Modal } from '@/components/ui/modal';
import { APPOINTMENT_STATUS_LABELS } from '@/features/appointments/types';
import { CustomerPicker } from '@/features/customers/components/customer-picker';
import { whatsappHref } from '@/features/customers/contact-links';
import { resolveLeadApiError } from '@/features/leads/errors';
import { useAcknowledgeLeadAttention, useLead, useUpdateLead } from '@/features/leads/hooks';
import {
    LEAD_HANDOFF_REASON_LABELS,
    LEAD_OUTCOME_LABELS,
    LEAD_SOURCE_LABELS,
    LEAD_STATUS_LABELS,
    type LeadDetail,
    type LeadHandoffReasonCode,
    type LeadOutcome,
    type LeadStatus,
    type LeadUpdatePayload,
} from '@/features/leads/types';
import { ApiError } from '@/lib/api/client';
import { dateTimeInTimeZone, resolveBusinessTimeZone } from '@/lib/business-time';
import { cn } from '@/lib/utils';

import { agendaHref, formatAppointmentWhen } from '../../../clientes/[id]/customer-upcoming-appointments';
import { LeadActivityTimeline } from './lead-activity';
import { LeadAppointmentPicker } from './lead-appointment-picker';
import { LeadAssigneeSelect } from './lead-assignee-select';
import { LeadConversationControl } from './lead-conversation-control';
import { LeadConversationHistory } from './lead-conversation-history';
import { LeadMessageComposer } from './lead-message-composer';
import { LeadNotes } from './lead-notes';

const INBOX_HREF = '/app/turnos/leads' as Route;
const WHATSAPP_SOURCE: LeadDetail['source'] = 'whatsapp_agent';

const STATUS_BADGE: Record<LeadStatus, string> = {
    new: 'bg-sky-100 text-sky-700',
    in_progress: 'bg-violet-100 text-violet-700',
    closed: 'bg-slate-200 text-slate-600',
};

const OUTLINE_BUTTON =
    'rounded-full border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:border-slate-900 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-50';
const PRIMARY_BUTTON =
    'rounded-full border border-slate-900 bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-200';
const DANGER_LINK = 'text-xs font-semibold text-rose-600 hover:text-rose-800 disabled:cursor-not-allowed disabled:opacity-50';

export function leadDetailDisplayName(lead: LeadDetail): string {
    const agent = lead.agent_state;
    return agent?.patient_name || agent?.whatsapp_profile_name || lead.customer?.display_name || agent?.phone_e164 || 'Sin nombre';
}

/**
 * `true` solo cuando el nombre mostrado es el que el paciente confirmó en el
 * chat (`patient_name`). El nombre de perfil de WhatsApp lo puede poner
 * cualquiera y cambia solo: nunca se muestra como si fuera el nombre real
 * sin aclararlo.
 */
export function leadNameIsConfirmed(lead: LeadDetail): boolean {
    return Boolean(lead.agent_state?.patient_name);
}

type LeadDetailClientProps = {
    leadId: string;
    /** `manage_leads`: todas las acciones. Sin él la pantalla es solo lectura. */
    canManage: boolean;
    /** `view_customers` (+ flag de Clientes): buscador de Customer y link a la ficha. */
    canViewCustomers: boolean;
    /** `view_appointments`: agenda del día en el selector y link a la agenda. */
    canViewAppointments: boolean;
    currentUserId: number | null;
    businessTimeZone: string | null;
};

/**
 * Detalle operativo del Lead (LEADS 05B): resumen, atención pendiente,
 * gestión CRM (estado/resultado/asignación), vínculos con Customer y turno,
 * notas e historial. Todas las mutaciones usan el PATCH / acknowledge
 * existentes; sus respuestas (detalle completo) reemplazan la cache.
 */
export function LeadDetailClient({
    leadId,
    canManage,
    canViewCustomers,
    canViewAppointments,
    currentUserId,
    businessTimeZone,
}: LeadDetailClientProps) {
    const timeZone = resolveBusinessTimeZone(businessTimeZone);
    const leadQuery = useLead(leadId);

    if (leadQuery.isLoading) {
        return <p role="status" className="px-3 py-10 text-center text-sm text-slate-500">Cargando lead…</p>;
    }

    if (leadQuery.isError || !leadQuery.data) {
        return <LeadLoadError error={leadQuery.error} onRetry={() => void leadQuery.refetch()} />;
    }

    const lead = leadQuery.data;

    return (
        <section className="space-y-4">
            <LeadHeader lead={lead} canManage={canManage} currentUserId={currentUserId} timeZone={timeZone} />
            {lead.needs_attention ? <AttentionAlert lead={lead} canManage={canManage} timeZone={timeZone} /> : null}

            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
                {/* En mobile la gestión va primero: es lo que se opera. */}
                <aside className="space-y-4 lg:order-last">
                    <ManagementCard lead={lead} canManage={canManage} currentUserId={currentUserId} timeZone={timeZone} />
                    <CustomerCard lead={lead} canManage={canManage} canViewCustomers={canViewCustomers} />
                    <AppointmentCard
                        lead={lead}
                        canManage={canManage}
                        canViewCustomers={canViewCustomers}
                        canViewAppointments={canViewAppointments}
                        timeZone={timeZone}
                    />
                </aside>
                <div className="min-w-0 space-y-4">
                    <AgentCard lead={lead} timeZone={timeZone} />
                    <LeadConversationHistory
                        leadId={lead.id}
                        timeZone={timeZone}
                        patientPhone={lead.agent_state?.phone_e164 ?? null}
                    />
                    {canManage && lead.conversation_control?.state === 'taken' ? (
                        <LeadMessageComposer leadId={lead.id} />
                    ) : null}
                    <LeadNotes leadId={lead.id} canManage={canManage} timeZone={timeZone} />
                    <LeadActivityTimeline activity={lead.activity} timeZone={timeZone} />
                </div>
            </div>
        </section>
    );
}

function LeadLoadError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
    const status = error instanceof ApiError ? error.status : null;
    const code = error instanceof ApiError ? (error.payload as { code?: string } | undefined)?.code : undefined;
    const definitive = status === 404 || status === 403;
    const message =
        status === 404
            ? 'No encontramos este lead. Puede que no exista o que pertenezca a otro negocio.'
            : code === 'plan_entitlement_required'
                ? 'Tu plan no incluye Leads.'
                : status === 403
                    ? 'No tenés permiso para ver este lead.'
                    : 'No pudimos cargar el lead.';
    return (
        <div role="alert" className="flex flex-col items-center gap-3 rounded-3xl border border-slate-200 bg-white px-4 py-10 text-center">
            <p className="text-sm text-slate-700">{message}</p>
            <div className="flex flex-wrap justify-center gap-2">
                {!definitive ? (
                    <button type="button" onClick={onRetry} className={OUTLINE_BUTTON}>
                        Reintentar
                    </button>
                ) : null}
                <Link href={INBOX_HREF} className={OUTLINE_BUTTON}>
                    Volver a la bandeja
                </Link>
            </div>
        </div>
    );
}

function Card({ title, label, children, actions }: { title: string; label?: string; children: ReactNode; actions?: ReactNode }) {
    return (
        <section aria-label={label ?? title} className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
                {actions}
            </div>
            <div className="mt-3 space-y-3">{children}</div>
        </section>
    );
}

function InlineError({ message }: { message: string | null }) {
    if (!message) return null;
    return (
        <p role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
            {message}
        </p>
    );
}

/** Mutación con error propio por tarjeta (los mensajes del backend se muestran tal cual). */
function useLeadPatch(leadId: string) {
    const mutation = useUpdateLead(leadId);
    const [error, setError] = useState<string | null>(null);
    const patch = async (payload: LeadUpdatePayload) => {
        setError(null);
        try {
            await mutation.mutateAsync(payload);
            return true;
        } catch (err) {
            setError(resolveLeadApiError(err, 'No pudimos guardar el cambio. Intentá nuevamente.'));
            return false;
        }
    };
    return { patch, pending: mutation.isPending, error, clearError: () => setError(null) };
}

// ── Header ───────────────────────────────────────────────────────────────────

function LeadHeader({
    lead,
    canManage,
    currentUserId,
    timeZone,
}: {
    lead: LeadDetail;
    canManage: boolean;
    currentUserId: number | null;
    timeZone: string;
}) {
    const agent = lead.agent_state;
    const name = leadDetailDisplayName(lead);
    const phone = agent?.phone_e164 && agent.phone_e164 !== name ? agent.phone_e164 : null;
    const closed = lead.status === 'closed';
    // El nombre mostrado viene del perfil de WhatsApp (nadie lo confirmó en
    // el chat): se aclara en vez de mostrarlo como si fuera un dato cierto
    const nameFromUnconfirmedProfile = !leadNameIsConfirmed(lead) && Boolean(agent?.whatsapp_profile_name) && name === agent?.whatsapp_profile_name;

    return (
        <header className="space-y-3 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
            <Link href={INBOX_HREF} className="text-xs font-semibold text-slate-500 hover:text-slate-900">
                ← Volver a la bandeja
            </Link>
            <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-2xl font-semibold text-slate-900">{name}</h2>
                {nameFromUnconfirmedProfile ? (
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
                        Nombre de perfil de WhatsApp, sin confirmar
                    </span>
                ) : null}
                <span className={cn('rounded-full px-2 py-0.5 text-xs font-semibold', STATUS_BADGE[lead.status])}>
                    {LEAD_STATUS_LABELS[lead.status]}
                    {closed && lead.outcome ? ` · ${LEAD_OUTCOME_LABELS[lead.outcome]}` : ''}
                </span>
                {agent?.urgency ? (
                    <span className="rounded-full bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-700">Urgente</span>
                ) : null}
                {lead.needs_attention ? (
                    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">Atención pendiente</span>
                ) : null}
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                <p className="text-sm text-slate-600">
                    {phone ? `${phone} · ` : ''}
                    {LEAD_SOURCE_LABELS[lead.source] ?? lead.source}
                </p>
                {lead.conversation_control ? null : <LeadWhatsappAction lead={lead} />}
            </div>
            {lead.conversation_control ? (
                <LeadConversationControl
                    leadId={lead.id}
                    control={lead.conversation_control}
                    canManage={canManage}
                    currentUserId={currentUserId}
                    timeZone={timeZone}
                    whatsappAction={<LeadWhatsappAction lead={lead} />}
                />
            ) : null}
            {agent?.reason ? <p className="text-sm text-slate-800">{agent.reason}</p> : null}
            <dl className="grid gap-x-6 gap-y-2 text-xs text-slate-500 sm:grid-cols-2 lg:grid-cols-4">
                <HeaderFact label="Ingresó" value={dateTimeInTimeZone(lead.created_at, timeZone)} />
                <HeaderFact label="Último mensaje" value={agent?.last_message_at ? dateTimeInTimeZone(agent.last_message_at, timeZone) : '—'} />
                <HeaderFact label="Asignado" value={lead.assigned_to?.display_name ?? 'Sin asignar'} />
                <HeaderFact label="Cliente" value={lead.customer?.display_name ?? 'Sin vincular'} />
                <HeaderFact
                    label="Turno"
                    value={lead.appointment?.start_at ? formatAppointmentWhen(lead.appointment.start_at, timeZone) : 'Sin vincular'}
                />
            </dl>
        </header>
    );
}

/**
 * Abre el chat con `https://wa.me/<dígitos>` (sin mensaje prellenado) solo para
 * Leads que llegaron por WhatsApp. Sin teléfono utilizable queda deshabilitado
 * con la explicación visible.
 */
function LeadWhatsappAction({ lead }: { lead: LeadDetail }) {
    if (lead.source !== WHATSAPP_SOURCE) return null;
    const href = whatsappHref(lead.agent_state?.phone_e164);
    if (!href) {
        return (
            <div className="flex flex-wrap items-center gap-2">
                <button
                    type="button"
                    disabled
                    aria-describedby="lead-whatsapp-unavailable"
                    className="min-h-11 cursor-not-allowed rounded-full border border-slate-200 px-4 text-sm font-semibold text-slate-400 md:min-h-0 md:py-1.5"
                >
                    Abrir WhatsApp
                </button>
                <span id="lead-whatsapp-unavailable" className="text-xs text-slate-500">
                    No hay un teléfono válido para abrir el chat.
                </span>
            </div>
        );
    }
    return (
        <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-11 items-center rounded-full bg-emerald-600 px-4 text-sm font-semibold text-white hover:bg-emerald-700 md:min-h-0 md:py-1.5"
        >
            Abrir WhatsApp
        </a>
    );
}

function HeaderFact({ label, value }: { label: string; value: string }) {
    return (
        <div>
            <dt>{label}</dt>
            <dd className="font-medium text-slate-800">{value}</dd>
        </div>
    );
}

// ── Atención pendiente ───────────────────────────────────────────────────────

function AttentionAlert({ lead, canManage, timeZone }: { lead: LeadDetail; canManage: boolean; timeZone: string }) {
    const mutation = useAcknowledgeLeadAttention(lead.id);
    const [error, setError] = useState<string | null>(null);

    const acknowledge = async () => {
        setError(null);
        try {
            // Idempotente en el backend: si otra persona ya la reconoció responde 200 y el detalle nuevo oculta la alerta.
            await mutation.mutateAsync();
        } catch (err) {
            setError(resolveLeadApiError(err, 'No pudimos marcar la atención. Intentá nuevamente.'));
        }
    };

    return (
        <div role="status" data-testid="lead-attention" className="flex flex-col gap-3 rounded-3xl border border-amber-300 bg-amber-50 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-1">
                <p className="text-sm font-semibold text-amber-900">Este lead pide la atención de una persona</p>
                <p className="text-xs text-amber-800">
                    {lead.needs_attention_at ? `Desde ${dateTimeInTimeZone(lead.needs_attention_at, timeZone)}. ` : ''}
                    {canManage ? 'Marcalo como atendido cuando alguien del equipo lo tome.' : 'Alguien del equipo con permiso de gestión debe tomarlo.'}
                </p>
                <InlineError message={error} />
            </div>
            {canManage ? (
                <button type="button" onClick={acknowledge} disabled={mutation.isPending} className={cn(PRIMARY_BUTTON, 'shrink-0')}>
                    {mutation.isPending ? 'Marcando…' : 'Marcar como atendido'}
                </button>
            ) : null}
        </div>
    );
}

// ── Gestión: estado / resultado / asignación ────────────────────────────────

function ManagementCard({
    lead,
    canManage,
    currentUserId,
    timeZone,
}: {
    lead: LeadDetail;
    canManage: boolean;
    currentUserId: number | null;
    timeZone: string;
}) {
    const { patch, pending, error, clearError } = useLeadPatch(lead.id);
    const [outcomeModal, setOutcomeModal] = useState<'close' | 'change' | null>(null);
    const closed = lead.status === 'closed';
    const assignedToMe = currentUserId != null && lead.assigned_to?.id === currentUserId;

    return (
        <Card title="Gestión">
            <div className="space-y-1">
                <p className="text-xs text-slate-500">Estado</p>
                <p className="text-sm font-semibold text-slate-900">
                    {LEAD_STATUS_LABELS[lead.status]}
                    {closed && lead.outcome ? ` · ${LEAD_OUTCOME_LABELS[lead.outcome]}` : ''}
                </p>
                {closed && lead.closed_at ? (
                    <p className="text-xs text-slate-500">
                        Cerrado el {dateTimeInTimeZone(lead.closed_at, timeZone)}
                        {lead.closed_by ? ` por ${lead.closed_by.display_name}` : ''}
                    </p>
                ) : null}
            </div>

            {canManage ? (
                <div className="flex flex-wrap gap-2">
                    {lead.status === 'new' ? (
                        <button type="button" disabled={pending} onClick={() => void patch({ status: 'in_progress' })} className={OUTLINE_BUTTON}>
                            Pasar a en gestión
                        </button>
                    ) : null}
                    {closed ? (
                        <button type="button" disabled={pending} onClick={() => {
                            clearError();
                            setOutcomeModal('change');
                        }} className={OUTLINE_BUTTON}>
                            Cambiar resultado
                        </button>
                    ) : (
                        <button type="button" disabled={pending} onClick={() => {
                            clearError();
                            setOutcomeModal('close');
                        }} className={OUTLINE_BUTTON}>
                            Cerrar lead
                        </button>
                    )}
                </div>
            ) : null}

            <div className="space-y-1 border-t border-slate-100 pt-3">
                <p className="text-xs text-slate-500">Asignado a</p>
                <p className={cn('text-sm font-semibold', lead.assigned_to ? 'text-slate-900' : 'italic text-slate-500')}>
                    {lead.assigned_to ? lead.assigned_to.display_name : 'Sin asignar'}
                    {assignedToMe ? ' (vos)' : ''}
                </p>
                {canManage ? (
                    <LeadAssigneeSelect
                        assignedTo={lead.assigned_to}
                        currentUserId={currentUserId}
                        pending={pending}
                        onAssign={(userId) => patch({ assigned_to: userId })}
                    />
                ) : null}
            </div>

            <InlineError message={outcomeModal ? null : error} />

            {canManage && outcomeModal ? (
                <OutcomeModal
                    mode={outcomeModal}
                    initialOutcome={lead.outcome}
                    pending={pending}
                    error={error}
                    onSubmit={async (outcome) => {
                        const ok = await patch(outcomeModal === 'close' ? { status: 'closed', outcome } : { outcome });
                        if (ok) setOutcomeModal(null);
                    }}
                    onClose={() => {
                        setOutcomeModal(null);
                        clearError();
                    }}
                />
            ) : null}
        </Card>
    );
}

function OutcomeModal({
    mode,
    initialOutcome,
    pending,
    error,
    onSubmit,
    onClose,
}: {
    mode: 'close' | 'change';
    initialOutcome: LeadOutcome | null;
    pending: boolean;
    error: string | null;
    onSubmit: (outcome: LeadOutcome) => void;
    onClose: () => void;
}) {
    const [outcome, setOutcome] = useState<'' | LeadOutcome>(initialOutcome ?? '');
    const unchanged = mode === 'change' && outcome === initialOutcome;

    const footer = (
        <div className="space-y-3">
            <InlineError message={error} />
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end sm:gap-3">
                <button
                    type="button"
                    onClick={onClose}
                    className="rounded-full border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900 sm:py-2"
                >
                    Cancelar
                </button>
                <button
                    type="button"
                    disabled={pending || !outcome || unchanged}
                    onClick={() => outcome && onSubmit(outcome)}
                    className={PRIMARY_BUTTON}
                >
                    {pending ? 'Guardando…' : mode === 'close' ? 'Cerrar lead' : 'Guardar resultado'}
                </button>
            </div>
        </div>
    );

    return (
        <Modal open eyebrow={null} title={mode === 'close' ? 'Cerrar lead' : 'Cambiar resultado'} onClose={onClose} footer={footer}>
            {mode === 'close' ? (
                <p className="text-sm text-slate-600">Un lead cerrado no se puede reabrir. Elegí cómo terminó la consulta.</p>
            ) : null}
            <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
                Resultado
                <select
                    value={outcome}
                    onChange={(event) => setOutcome(event.target.value as '' | LeadOutcome)}
                    className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm font-normal text-slate-700 focus:border-slate-900 focus:outline-none"
                >
                    <option value="" disabled>
                        Elegí un resultado
                    </option>
                    {Object.entries(LEAD_OUTCOME_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>
                            {label}
                        </option>
                    ))}
                </select>
            </label>
            {!outcome ? <p className="text-xs text-slate-500">El resultado es obligatorio para cerrar.</p> : null}
        </Modal>
    );
}

// ── Customer ────────────────────────────────────────────────────────────────

function CustomerCard({ lead, canManage, canViewCustomers }: { lead: LeadDetail; canManage: boolean; canViewCustomers: boolean }) {
    const { patch, pending, error, clearError } = useLeadPatch(lead.id);
    const [picking, setPicking] = useState(false);
    const canPick = canManage && canViewCustomers;

    return (
        <Card title="Cliente">
            {lead.customer ? (
                <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="min-w-0 truncate text-sm font-semibold text-slate-900">{lead.customer.display_name}</p>
                    {canViewCustomers ? (
                        <Link href={`/app/clientes/${lead.customer.id}` as Route} className="text-xs font-semibold text-slate-600 hover:text-slate-900">
                            Ver ficha
                        </Link>
                    ) : null}
                </div>
            ) : (
                <p className="text-sm italic text-slate-500">Sin cliente vinculado</p>
            )}

            {picking ? (
                <div className="space-y-2">
                    <CustomerPicker
                        value={null}
                        canCreate={false}
                        emptyHint="Escribí al menos 2 caracteres para buscar un cliente existente."
                        onSelect={async (customer) => {
                            if (await patch({ customer: customer.id })) setPicking(false);
                        }}
                    />
                    <button
                        type="button"
                        onClick={() => {
                            setPicking(false);
                            clearError();
                        }}
                        className="text-xs font-semibold text-slate-600 underline hover:text-slate-900"
                    >
                        Cancelar
                    </button>
                </div>
            ) : canManage ? (
                <div className="flex flex-wrap items-center gap-3">
                    {canPick ? (
                        <button type="button" disabled={pending} onClick={() => setPicking(true)} className={OUTLINE_BUTTON}>
                            {lead.customer ? 'Cambiar cliente' : 'Vincular cliente'}
                        </button>
                    ) : null}
                    {lead.customer ? (
                        <button type="button" disabled={pending} onClick={() => void patch({ customer: null })} className={DANGER_LINK}>
                            Desvincular
                        </button>
                    ) : null}
                </div>
            ) : null}
            {pending ? <p role="status" className="text-xs text-slate-500">Guardando…</p> : null}
            <InlineError message={error} />
        </Card>
    );
}

// ── Appointment ─────────────────────────────────────────────────────────────

function AppointmentCard({
    lead,
    canManage,
    canViewCustomers,
    canViewAppointments,
    timeZone,
}: {
    lead: LeadDetail;
    canManage: boolean;
    canViewCustomers: boolean;
    canViewAppointments: boolean;
    timeZone: string;
}) {
    const { patch, pending, error, clearError } = useLeadPatch(lead.id);
    const [picking, setPicking] = useState(false);
    const appointment = lead.appointment;
    const canPick = canManage && (canViewAppointments || (canViewCustomers && Boolean(lead.customer)));

    return (
        <Card title="Turno">
            {appointment ? (
                <div className="space-y-1" data-testid="lead-appointment">
                    <p className="text-sm font-semibold text-slate-900">
                        {appointment.start_at ? formatAppointmentWhen(appointment.start_at, timeZone) : 'Turno vinculado'}
                    </p>
                    <p className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                        {appointment.service_name ? <span>{appointment.service_name}</span> : null}
                        {appointment.status ? (
                            <span className="rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-600">
                                {APPOINTMENT_STATUS_LABELS[appointment.status] ?? appointment.status}
                            </span>
                        ) : null}
                    </p>
                    {canViewAppointments && appointment.start_at ? (
                        <Link
                            href={agendaHref({ id: appointment.id, start_at: appointment.start_at }, timeZone) as Route}
                            className="inline-block text-xs font-semibold text-slate-600 hover:text-slate-900"
                        >
                            Ver en la agenda
                        </Link>
                    ) : null}
                </div>
            ) : (
                <p className="text-sm italic text-slate-500">Sin turno vinculado</p>
            )}

            {canManage ? (
                <div className="flex flex-wrap items-center gap-3">
                    {canPick ? (
                        <button
                            type="button"
                            disabled={pending}
                            onClick={() => {
                                clearError();
                                setPicking(true);
                            }}
                            className={OUTLINE_BUTTON}
                        >
                            {appointment ? 'Cambiar turno' : 'Vincular turno'}
                        </button>
                    ) : null}
                    {appointment ? (
                        <button type="button" disabled={pending} onClick={() => void patch({ appointment: null })} className={DANGER_LINK}>
                            Desvincular
                        </button>
                    ) : null}
                </div>
            ) : null}
            <InlineError message={picking ? null : error} />

            {picking ? (
                <LeadAppointmentPicker
                    customer={lead.customer}
                    currentAppointmentId={appointment?.id ?? null}
                    canViewCustomers={canViewCustomers}
                    canViewAppointments={canViewAppointments}
                    timeZone={timeZone}
                    pending={pending}
                    error={error}
                    onSelect={async (appointmentId) => {
                        if (await patch({ appointment: appointmentId })) setPicking(false);
                    }}
                    onClose={() => {
                        setPicking(false);
                        clearError();
                    }}
                />
            ) : null}
        </Card>
    );
}

// ── Agente ──────────────────────────────────────────────────────────────────

const PATIENT_ASKED_HUMAN: LeadHandoffReasonCode = 'patient_asked_human';

function handoffReasonCodes(reasons: unknown[]): LeadHandoffReasonCode[] {
    const codes = reasons
        .map((reason) => (reason && typeof reason === 'object' ? (reason as { code?: unknown }).code : null))
        .filter((code): code is string => typeof code === 'string');
    return Array.from(new Set(codes)) as LeadHandoffReasonCode[];
}

function handoffReasonLabel(code: LeadHandoffReasonCode): string {
    return LEAD_HANDOFF_REASON_LABELS[code] ?? 'Otro motivo';
}

/**
 * Lo que contó el agente, solo lo útil para operar: resumen, motivo, horario
 * preferido y por qué se pidió una persona. Nunca ids externos, versiones,
 * hashes ni datos del canal.
 */
function AgentCard({ lead, timeZone }: { lead: LeadDetail; timeZone: string }) {
    const agent = lead.agent_state;
    if (!agent) {
        return (
            <Card title="Conversación con el agente">
                <p className="text-sm text-slate-500">El agente todavía no envió información de esta conversación.</p>
            </Card>
        );
    }
    const codes = agent.handoff_requested ? handoffReasonCodes(agent.handoff_reasons ?? []) : [];
    // El motivo real registrado decide el título: quién lo pidió, no una
    // etiqueta genérica de "pidió una persona" para cualquier motivo
    const patientAskedHuman = codes.includes(PATIENT_ASKED_HUMAN);
    const botDerivedCodes = codes.filter((code) => code !== PATIENT_ASKED_HUMAN);

    return (
        <Card
            title="Conversación con el agente"
            actions={
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                    {agent.agent_status === 'active' ? 'Conversación activa' : 'Conversación finalizada'}
                </span>
            }
        >
            <AgentFact label="Resumen" value={agent.summary} />
            <AgentFact label="Motivo de la consulta" value={agent.reason} />
            <AgentFact label="Horario preferido" value={agent.preferred_time} />
            <AgentFact label="Nombre confirmado por el paciente" value={agent.patient_name} />
            {agent.whatsapp_profile_name && agent.whatsapp_profile_name !== agent.patient_name ? (
                <AgentFact label="Nombre de perfil de WhatsApp (sin confirmar)" value={agent.whatsapp_profile_name} />
            ) : null}
            {patientAskedHuman ? (
                <div>
                    <p className="text-xs text-slate-500">
                        El paciente pidió una persona
                        {agent.handoff_requested_at ? ` el ${dateTimeInTimeZone(agent.handoff_requested_at, timeZone)}` : ''}
                    </p>
                    <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-slate-800">
                        <li>{handoffReasonLabel(PATIENT_ASKED_HUMAN)}</li>
                    </ul>
                </div>
            ) : null}
            {botDerivedCodes.length > 0 ? (
                <div>
                    <p className="text-xs text-slate-500">El bot derivó la consulta para coordinar un turno</p>
                    <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-slate-800">
                        {botDerivedCodes.map((code) => (
                            <li key={code}>{handoffReasonLabel(code)}</li>
                        ))}
                    </ul>
                </div>
            ) : null}
            {!agent.summary && !agent.reason && !agent.preferred_time && !agent.handoff_requested ? (
                <p className="text-sm text-slate-500">El agente no dejó un resumen todavía.</p>
            ) : null}
        </Card>
    );
}


function AgentFact({ label, value }: { label: string; value: string | null }) {
    if (!value) return null;
    return (
        <div>
            <p className="text-xs text-slate-500">{label}</p>
            <p className="whitespace-pre-wrap break-words text-sm text-slate-800">{value}</p>
        </div>
    );
}
