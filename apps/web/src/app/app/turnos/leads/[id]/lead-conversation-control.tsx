"use client";

import { useEffect, useRef, useState, type ReactNode } from 'react';

import { Modal } from '@/components/ui/modal';
import {
    conversationCommandRequestFeedback,
    conversationControlErrorMessage,
    type ConversationCommandFeedback,
} from '@/features/leads/errors';
import { useConversationCommand } from '@/features/leads/hooks';
import type { ConversationCommandAction, ConversationControlState, LeadConversationControl } from '@/features/leads/types';
import { dateTimeInTimeZone } from '@/lib/business-time';
import { cn } from '@/lib/utils';

// `active` es el modo de funcionamiento (nadie tomó la conversación), no una
// confirmación de que el bot esté respondiendo bien: eso no lo sabe este
// estado (lo sabría, por ejemplo, el estado de entrega de sus mensajes)
const STATE_PILL: Record<ConversationControlState, { label: string; className: string }> = {
    active: { label: 'Bot habilitado', className: 'bg-slate-100 text-slate-700' },
    takeover_pending: { label: 'Procesando', className: 'bg-amber-100 text-amber-800' },
    taken: { label: 'Conversación tomada', className: 'bg-indigo-100 text-indigo-700' },
    release_pending: { label: 'Procesando', className: 'bg-amber-100 text-amber-800' },
    error: { label: 'Error de control', className: 'bg-rose-100 text-rose-700' },
};

const ACTION_COPY: Record<
    ConversationCommandAction,
    { label: string; retryLabel: string; pendingLabel: string; title: string; body: string[] }
> = {
    takeover: {
        label: 'Tomar conversación',
        retryLabel: 'Reintentar tomar conversación',
        pendingLabel: 'Tomando conversación…',
        title: '¿Tomar esta conversación?',
        body: [
            'El bot dejará de responder mensajes nuevos en este chat hasta que vuelvas a habilitarlo. Podés continuar la atención desde WhatsApp.',
        ],
    },
    release: {
        label: 'Reanudar bot',
        retryLabel: 'Reintentar reanudar bot',
        pendingLabel: 'Reanudando bot…',
        title: '¿Reanudar el bot?',
        body: [
            'El bot volverá a responder a partir del próximo mensaje nuevo del paciente.',
            'Los mensajes recibidos mientras la conversación estuvo tomada no serán respondidos retroactivamente.',
        ],
    },
};

const BUTTON_BASE =
    'inline-flex min-h-11 items-center gap-2 rounded-full px-4 text-sm font-semibold transition disabled:cursor-not-allowed md:min-h-0 md:py-1.5';
const PRIMARY = 'border border-slate-900 bg-slate-900 text-white hover:bg-slate-800 disabled:border-slate-200 disabled:bg-slate-200 disabled:text-slate-500';
const OUTLINE = 'border border-slate-300 bg-white text-slate-800 hover:border-slate-900 hover:text-slate-900 disabled:border-slate-200 disabled:text-slate-400';

// Normal delivery (Celery kick) resolves in well under a second; this only
// fires to flag an abnormal stall (e.g. a down/broken worker, as happened
// once in QA) — it never claims success, just stops the silent indefinite spinner.
const PENDING_STALL_WARNING_MS = 20_000;

/** Mensaje de cierre al ver pasar el estado de `*_pending` al resultado (una sola vez por transición). */
function completionMessage(previous: ConversationControlState | undefined, current: ConversationControlState): string | null {
    if (previous === 'takeover_pending' && current === 'taken') return 'Conversación tomada.';
    if (previous === 'release_pending' && current === 'active') return 'Bot reanudado.';
    return null;
}

type LeadConversationControlProps = {
    leadId: string;
    control: LeadConversationControl;
    /** `manage_leads`: puede pedir takeover/release. Sin él solo ve el estado. Es UX: decide el backend. */
    canManage: boolean;
    currentUserId: number | null;
    timeZone: string;
    /** Botón "Abrir WhatsApp" existente: nunca dispara takeover. */
    whatsappAction: ReactNode;
};

/**
 * Control humano de la conversación (MIRUBRO TAKEOVER 05B): tomar el chat
 * (pausa el bot) y reanudar el bot. Muestra el estado tal como lo informa el
 * backend; mientras está `*_pending` el detalle se refresca solo (`useLead`).
 * MiRubro no envía mensajes: la atención sigue en WhatsApp.
 */
export function LeadConversationControl({
    leadId,
    control,
    canManage,
    currentUserId,
    timeZone,
    whatsappAction,
}: LeadConversationControlProps) {
    const takeover = useConversationCommand(leadId, 'takeover');
    const release = useConversationCommand(leadId, 'release');
    const [confirming, setConfirming] = useState<ConversationCommandAction | null>(null);
    const [feedback, setFeedback] = useState<ConversationCommandFeedback | null>(null);

    const { state } = control;
    const previousState = useRef(state);
    useEffect(() => {
        const message = completionMessage(previousState.current, state);
        previousState.current = state;
        if (message) setFeedback({ tone: 'info', message });
    }, [state]);

    // Clock purely client-side (no `last_command_at` in the API yet): resets
    // whenever `state` changes, so a page reload while already stuck under-counts
    // the real wait instead of over-claiming a stall. Polling itself never stops.
    const [stalled, setStalled] = useState(false);
    useEffect(() => {
        setStalled(false);
        if (state !== 'takeover_pending' && state !== 'release_pending') return;
        const timer = setTimeout(() => setStalled(true), PENDING_STALL_WARNING_MS);
        return () => clearTimeout(timer);
    }, [state]);

    const requesting = takeover.isPending || release.isPending;
    const actionable = canManage && control.available;
    // Desde `error` se reintenta lo último que se pidió (lo dice el backend, no se infiere).
    const nextAction: ConversationCommandAction | null =
        state === 'active' ? 'takeover' : state === 'taken' ? 'release' : state === 'error' ? control.last_action : null;
    const pendingAction: ConversationCommandAction | null =
        state === 'takeover_pending' ? 'takeover' : state === 'release_pending' ? 'release' : null;

    const submit = async (action: ConversationCommandAction) => {
        setFeedback(null);
        try {
            await (action === 'takeover' ? takeover : release).mutateAsync();
        } catch (err) {
            // La mutation ya refrescó el Lead: se muestra el estado real junto al aviso.
            setFeedback(conversationCommandRequestFeedback(err));
        } finally {
            setConfirming(null);
        }
    };

    const takenBy =
        state === 'taken' && control.taken_by
            ? currentUserId != null && control.taken_by.id === currentUserId
                ? 'Tomada por vos'
                : `Tomada por ${control.taken_by.display_name}`
            : null;
    const takenSince = state === 'taken' && control.taken_at ? `desde ${dateTimeInTimeZone(control.taken_at, timeZone)}` : null;
    const takenDetail = [takenBy, takenSince].filter(Boolean).join(' · ');

    const pill = STATE_PILL[state] ?? STATE_PILL.error;

    return (
        <div data-testid="lead-conversation-control" data-state={state} className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
                <span className={cn('rounded-full px-2.5 py-1 text-xs font-semibold', pill.className)}>{pill.label}</span>
                {whatsappAction}
                {actionable && pendingAction ? (
                    <button type="button" disabled className={cn(BUTTON_BASE, OUTLINE)}>
                        <Spinner />
                        {ACTION_COPY[pendingAction].pendingLabel}
                    </button>
                ) : null}
                {actionable && nextAction ? (
                    <button
                        type="button"
                        disabled={requesting}
                        onClick={() => {
                            setFeedback(null);
                            setConfirming(nextAction);
                        }}
                        className={cn(BUTTON_BASE, nextAction === 'takeover' ? PRIMARY : OUTLINE)}
                    >
                        {requesting ? <Spinner /> : null}
                        {state === 'error' ? ACTION_COPY[nextAction].retryLabel : ACTION_COPY[nextAction].label}
                    </button>
                ) : null}
            </div>

            {state === 'takeover_pending' ? <p className="text-xs text-slate-600">Estamos pausando el bot.</p> : null}
            {state === 'release_pending' ? <p className="text-xs text-slate-600">Estamos devolviendo la conversación al bot.</p> : null}
            {stalled ? (
                <p role="alert" className="rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                    Esto está tardando más de lo esperado. Todavía puede resolverse solo; si sigue así, avisá a soporte técnico antes de asumir que ya se aplicó.
                </p>
            ) : null}
            {state === 'taken' ? (
                <p className="text-xs text-slate-600">
                    {takenDetail ? `${takenDetail}. ` : ''}El bot está pausado.
                </p>
            ) : null}
            {state === 'error' ? (
                <div role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                    {conversationControlErrorMessage(control.last_error_code)}
                </div>
            ) : null}
            {!control.available ? (
                <p className="text-xs text-slate-500">
                    {state === 'active'
                        ? 'El bot está habilitado para este paciente (este estado no confirma que sus mensajes se estén entregando: revisá el historial de la conversación). Pausarlo o retomarlo manualmente desde acá no está disponible: el control manual no está habilitado para este canal.'
                        : 'El control manual (pausar/retomar el bot) no está habilitado para este canal.'}
                </p>
            ) : null}
            {feedback ? (
                <p
                    role={feedback.tone === 'error' ? 'alert' : 'status'}
                    className={cn(
                        'rounded-2xl px-3 py-2 text-xs',
                        feedback.tone === 'error' ? 'border border-rose-200 bg-rose-50 text-rose-700' : 'bg-slate-100 text-slate-700',
                    )}
                >
                    {feedback.message}
                </p>
            ) : null}

            {actionable && confirming ? (
                <ConfirmCommandModal
                    action={confirming}
                    pending={requesting}
                    onConfirm={() => void submit(confirming)}
                    onClose={() => {
                        if (!requesting) setConfirming(null);
                    }}
                />
            ) : null}
        </div>
    );
}

function Spinner() {
    return <span aria-hidden="true" className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />;
}

function ConfirmCommandModal({
    action,
    pending,
    onConfirm,
    onClose,
}: {
    action: ConversationCommandAction;
    pending: boolean;
    onConfirm: () => void;
    onClose: () => void;
}) {
    const copy = ACTION_COPY[action];
    const footer = (
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end sm:gap-3">
            <button
                type="button"
                onClick={onClose}
                disabled={pending}
                className="rounded-full border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-50 sm:py-2"
            >
                Cancelar
            </button>
            <button
                type="button"
                onClick={onConfirm}
                disabled={pending}
                className="rounded-full border border-slate-900 bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-200 sm:py-2"
            >
                {pending ? copy.pendingLabel : copy.label}
            </button>
        </div>
    );
    return (
        <Modal open eyebrow={null} title={copy.title} onClose={onClose} footer={footer}>
            <div className="space-y-2 text-sm text-slate-600">
                {copy.body.map((paragraph) => (
                    <p key={paragraph}>{paragraph}</p>
                ))}
            </div>
        </Modal>
    );
}
