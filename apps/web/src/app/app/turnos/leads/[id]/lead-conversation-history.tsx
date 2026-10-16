"use client";

import { useEffect, useRef, useState } from 'react';

import { useLeadMessages } from '@/features/leads/hooks';
import {
    LEAD_MESSAGE_SENDER_LABELS,
    LEAD_MESSAGE_STATUS_LABELS,
    LEAD_MESSAGE_STATUS_UNKNOWN_LABEL,
    type LeadMessage,
} from '@/features/leads/types';
import { dateInTimeZone, timeInTimeZone } from '@/lib/business-time';
import { cn } from '@/lib/utils';

const STATUS_BADGE: Record<string, string> = {
    sent: 'bg-slate-100 text-slate-600',
    delivered: 'bg-slate-100 text-slate-600',
    read: 'bg-sky-100 text-sky-700',
    failed: 'bg-rose-100 text-rose-700',
    unknown: 'bg-amber-50 text-amber-700',
};

/** Separador de día en la zona horaria del negocio ("Hoy"/"Ayer" si corresponde). */
function dayLabel(value: string, timeZone: string): string {
    const day = dateInTimeZone(value, timeZone);
    const today = dateInTimeZone(new Date(), timeZone);
    const yesterday = dateInTimeZone(new Date(Date.now() - 86_400_000), timeZone);
    if (day === today) return 'Hoy';
    if (day === yesterday) return 'Ayer';
    const [year, month, dayOfMonth] = day.split('-');
    return `${dayOfMonth}/${month}/${year}`;
}

type Group = { day: string; messages: LeadMessage[] };

/** Agrupa en bloques consecutivos del mismo día local, sin reordenar. */
function groupByDay(messages: LeadMessage[], timeZone: string): Group[] {
    const groups: Group[] = [];
    for (const message of messages) {
        const day = dateInTimeZone(message.sent_at, timeZone);
        const last = groups.at(-1);
        if (last && last.day === day) last.messages.push(message);
        else groups.push({ day, messages: [message] });
    }
    return groups;
}

type LeadConversationHistoryProps = {
    leadId: string;
    timeZone: string;
    /** Para identificar los mensajes del paciente ("izquierda... y con su número"). */
    patientPhone: string | null;
};

/**
 * Historial real de la conversación de WhatsApp del Lead (LEADS 05C):
 * paciente a la izquierda, agente (bot/recepción) a la derecha, orden
 * cronológico, separadores por día, estado de entrega cuando hay evidencia.
 * Actualiza solo (polling incremental, ver `useLeadMessages`) sin recargar la
 * página. Nunca reconstruye mensajes a partir del resumen: si no hay
 * historial lo dice explícitamente.
 */
export function LeadConversationHistory({ leadId, timeZone, patientPhone }: LeadConversationHistoryProps) {
    const { messages, status, loadedOnce, refetch } = useLeadMessages(leadId);
    const scrollRef = useRef<HTMLDivElement>(null);
    const wasNearBottomRef = useRef(true);
    const previousCountRef = useRef(0);

    // Conserva la posición de lectura: solo baja solo si ya estaba cerca del
    // final (o es la primera carga). Si el usuario está leyendo mensajes
    // anteriores (scrolleado arriba), un mensaje nuevo no le mueve la vista.
    useEffect(() => {
        const el = scrollRef.current;
        if (!el) return;
        const grew = messages.length > previousCountRef.current;
        previousCountRef.current = messages.length;
        if (grew && wasNearBottomRef.current) {
            el.scrollTop = el.scrollHeight;
        }
    }, [messages]);

    const handleScroll = () => {
        const el = scrollRef.current;
        if (!el) return;
        wasNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    };

    const groups = groupByDay(messages, timeZone);

    return (
        <section aria-label="Conversación de WhatsApp" className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Conversación de WhatsApp</h3>
                {status === 'error' ? (
                    <button type="button" onClick={() => refetch()} className="text-xs font-semibold text-slate-600 underline">
                        Reintentar
                    </button>
                ) : null}
            </div>

            {status === 'loading' && !loadedOnce ? (
                <p role="status" className="mt-3 text-sm text-slate-500">
                    Cargando conversación…
                </p>
            ) : status === 'error' && messages.length === 0 ? (
                <p role="alert" className="mt-3 text-sm text-rose-600">
                    No pudimos cargar la conversación.
                </p>
            ) : loadedOnce && messages.length === 0 ? (
                <p className="mt-3 text-sm text-slate-500">No hay historial de mensajes anterior para este lead.</p>
            ) : (
                <div
                    ref={scrollRef}
                    onScroll={handleScroll}
                    data-testid="lead-conversation-scroll"
                    className="mt-3 max-h-[28rem] space-y-4 overflow-y-auto pr-1"
                >
                    {groups.map((group) => (
                        <div key={group.day} className="space-y-2">
                            <div className="sticky top-0 z-10 flex justify-center">
                                <span className="rounded-full bg-slate-100 px-3 py-0.5 text-[11px] font-medium text-slate-500">
                                    {dayLabel(group.messages[0].sent_at, timeZone)}
                                </span>
                            </div>
                            {group.messages.map((message) => (
                                <MessageBubble key={message.id} message={message} timeZone={timeZone} patientPhone={patientPhone} />
                            ))}
                        </div>
                    ))}
                </div>
            )}
        </section>
    );
}

function MessageBubble({
    message,
    timeZone,
    patientPhone,
}: {
    message: LeadMessage;
    timeZone: string;
    patientPhone: string | null;
}) {
    const fromPatient = message.role === 'user';
    const senderLabel = fromPatient
        ? ['Paciente', patientPhone].filter(Boolean).join(' · ')
        : message.sender === 'staff' && message.authored_by
            ? message.authored_by.display_name
            : LEAD_MESSAGE_SENDER_LABELS[message.sender];

    return (
        <div className={cn('flex', fromPatient ? 'justify-start' : 'justify-end')}>
            <div
                data-testid="lead-message-bubble"
                data-role={message.role}
                className={cn(
                    'max-w-[80%] rounded-2xl px-3 py-2 text-sm shadow-sm',
                    fromPatient ? 'bg-slate-100 text-slate-800' : 'bg-brand-600 text-white',
                )}
            >
                <p className={cn('text-[11px] font-semibold', fromPatient ? 'text-slate-500' : 'text-white/80')}>{senderLabel}</p>
                <p className="mt-0.5 whitespace-pre-wrap break-words">{message.text}</p>
                <div className={cn('mt-1 flex items-center gap-1.5 text-[10px]', fromPatient ? 'text-slate-400' : 'text-white/70')}>
                    <span>{timeInTimeZone(message.sent_at, timeZone)}</span>
                    {!fromPatient ? (
                        <span className={cn('rounded-full px-1.5 py-0.5 font-medium', STATUS_BADGE[message.status ?? 'unknown'])}>
                            {message.status ? LEAD_MESSAGE_STATUS_LABELS[message.status] : LEAD_MESSAGE_STATUS_UNKNOWN_LABEL}
                        </span>
                    ) : null}
                </div>
            </div>
        </div>
    );
}
