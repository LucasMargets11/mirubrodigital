"use client";

import { useState } from 'react';

import { sendLeadMessageErrorMessage } from '@/features/leads/errors';
import { useSendLeadMessage } from '@/features/leads/hooks';
import { LEAD_MESSAGE_TEXT_MAX_LENGTH } from '@/features/leads/types';
import { cn } from '@/lib/utils';

type LeadMessageComposerProps = {
    leadId: string;
};

/**
 * Responder desde el chat (MIRUBRO HUMAN MESSAGES): textarea + botón de
 * envío. Solo se monta cuando `conversation_control.state === 'taken'` (ver
 * `lead-detail-client.tsx`), mismo criterio de gating que el resto del
 * control de la conversación.
 *
 * El POST solo confirma que el mensaje se ACEPTÓ para envío (outbox local),
 * nunca que llegó al paciente: nunca se muestra un estado "enviado" acá.
 * El mensaje nuevo (y su estado real sent/delivered/read/failed) aparece
 * solo, vía el polling de `LeadConversationHistory` ya existente, etiquetado
 * con quién de recepción lo escribió (`authored_by`).
 *
 * Límite conocido (reportado al usuario, no resuelto en esta tarea): si el
 * agente rechaza el mensaje de forma terminal después de aceptarlo acá
 * (por ejemplo `outside_service_window` o `conversation_not_taken`, recién
 * detectado en la entrega asíncrona), ese error queda registrado en el
 * outbox del backend pero todavía no se refleja en vivo en este composer.
 */
export function LeadMessageComposer({ leadId }: LeadMessageComposerProps) {
    const [text, setText] = useState('');
    const [error, setError] = useState<string | null>(null);
    const mutation = useSendLeadMessage(leadId);

    const trimmedLength = text.trim().length;
    const tooLong = text.length > LEAD_MESSAGE_TEXT_MAX_LENGTH;
    const canSend = trimmedLength > 0 && !tooLong && !mutation.isPending;

    const submit = async () => {
        if (!canSend) return;
        setError(null);
        try {
            await mutation.mutateAsync(text);
            setText('');
        } catch (err) {
            setError(sendLeadMessageErrorMessage(err));
        }
    };

    return (
        <section aria-label="Responder desde el chat" className="space-y-2 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Responder desde el chat</h3>
            <form
                onSubmit={(event) => {
                    event.preventDefault();
                    void submit();
                }}
                className="space-y-2"
            >
                <textarea
                    value={text}
                    onChange={(event) => setText(event.target.value)}
                    disabled={mutation.isPending}
                    placeholder="Escribí un mensaje para el paciente…"
                    rows={3}
                    aria-label="Mensaje para el paciente"
                    className="w-full resize-none rounded-2xl border border-slate-200 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:border-slate-900 focus:outline-none disabled:cursor-not-allowed disabled:bg-slate-50"
                />
                <div className="flex items-center justify-between gap-2">
                    <span className={cn('text-xs', tooLong ? 'font-semibold text-rose-600' : 'text-slate-400')}>
                        {text.length}/{LEAD_MESSAGE_TEXT_MAX_LENGTH}
                    </span>
                    <button
                        type="submit"
                        disabled={!canSend}
                        className="inline-flex min-h-11 items-center gap-2 rounded-full border border-slate-900 bg-slate-900 px-4 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-200 disabled:text-slate-500 md:min-h-0 md:py-1.5"
                    >
                        {mutation.isPending ? <Spinner /> : null}
                        {mutation.isPending ? 'Enviando…' : 'Enviar'}
                    </button>
                </div>
            </form>
            {error ? (
                <p role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                    {error}
                </p>
            ) : null}
            <p className="text-xs text-slate-500">
                El mensaje aparece abajo, en la conversación, apenas lo confirma el bot (no es instantáneo).
            </p>
        </section>
    );
}

function Spinner() {
    return <span aria-hidden="true" className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />;
}
