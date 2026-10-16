import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';

import {
    acknowledgeLeadAttention,
    createLeadNote,
    deleteLeadNote,
    getLead,
    listLeadAssignees,
    listLeadMessages,
    listLeadNotes,
    listLeads,
    releaseLead,
    sendLeadMessage,
    takeoverLead,
    updateLead,
    updateLeadNote,
} from './api';
import type { ConversationCommandAction, LeadDetail, LeadFilters, LeadMessage, LeadUpdatePayload } from './types';

export const leadsBaseKey = ['appointments', 'leads'];
const leadsListKey = [...leadsBaseKey, 'list'];

export function leadDetailKey(id: string) {
    return [...leadsBaseKey, 'detail', id];
}

function leadNotesKey(id: string) {
    return [...leadsBaseKey, 'notes', id];
}

/** Bandeja paginada. Conserva la página anterior mientras carga la siguiente (sin parpadeo). */
export function useLeads(filters: LeadFilters) {
    return useQuery({
        queryKey: [...leadsListKey, filters],
        queryFn: () => listLeads(filters),
        placeholderData: keepPreviousData,
    });
}

/** Intervalo de refresco mientras el agente confirma un takeover/release (entrega async por Celery). */
export const LEAD_CONVERSATION_POLL_MS = 2500;

/**
 * Polling SOLO mientras el control está `*_pending`; se corta solo al llegar a
 * `active`/`taken`/`error` (o si el Lead no tiene control).
 */
export function leadConversationPollInterval(lead: LeadDetail | undefined): number | false {
    const state = lead?.conversation_control?.state;
    return state === 'takeover_pending' || state === 'release_pending' ? LEAD_CONVERSATION_POLL_MS : false;
}

export function useLead(id: string) {
    return useQuery({
        queryKey: leadDetailKey(id),
        queryFn: () => getLead(id),
        enabled: !!id,
        // 404/403 son definitivos: no reintentar.
        retry: false,
        refetchInterval: (query) => leadConversationPollInterval(query.state.data),
    });
}

/**
 * Asignables del Business (LEADS 05B.1). Solo se pide con `manage_leads`
 * (`enabled`): sin él no hay selector. No depende del Lead.
 */
export function useLeadAssignees({ enabled = true }: { enabled?: boolean } = {}) {
    return useQuery({
        queryKey: [...leadsBaseKey, 'assignees'],
        queryFn: listLeadAssignees,
        enabled,
        staleTime: 60_000,
    });
}

/**
 * PATCH y acknowledge responden el detalle completo: se escribe en cache tal
 * cual (incluye la `activity` nueva) y se invalida la bandeja, cuyo orden y
 * filtros dependen de estado/atención/asignación.
 */
function applyLeadDetail(queryClient: QueryClient, lead: LeadDetail) {
    queryClient.setQueryData(leadDetailKey(lead.id), lead);
    return queryClient.invalidateQueries({ queryKey: leadsListKey });
}

export function useUpdateLead(id: string) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: LeadUpdatePayload) => updateLead(id, payload),
        onSuccess: (lead) => applyLeadDetail(queryClient, lead),
    });
}

export function useAcknowledgeLeadAttention(id: string) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: () => acknowledgeLeadAttention(id),
        onSuccess: (lead) => applyLeadDetail(queryClient, lead),
    });
}

/**
 * Takeover/release (MIRUBRO TAKEOVER 05B). La respuesta solo trae el estado
 * inicial: no se escribe en cache ni se adelanta `taken`; se refrescan detalle
 * (que arranca el polling si quedó `*_pending`) y bandeja. También tras error
 * (409 acción opuesta en curso, 503 apagado): el estado real puede ser otro.
 * Sin retry del frontend: el reintento durable lo hace el backend.
 */
export function useConversationCommand(id: string, action: ConversationCommandAction) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: () => (action === 'takeover' ? takeoverLead(id) : releaseLead(id)),
        retry: false,
        onSettled: () =>
            Promise.all([
                queryClient.invalidateQueries({ queryKey: leadDetailKey(id) }),
                queryClient.invalidateQueries({ queryKey: leadsListKey }),
            ]),
    });
}

export function useLeadNotes(leadId: string, params: { limit?: number } = {}) {
    return useQuery({
        queryKey: [...leadNotesKey(leadId), params],
        queryFn: () => listLeadNotes(leadId, params),
        enabled: !!leadId,
    });
}

/** Las notas no generan `activity`; el detalle también trae `notes`, por eso se refrescan ambos. */
function invalidateNotes(queryClient: QueryClient, leadId: string) {
    return Promise.all([
        queryClient.invalidateQueries({ queryKey: leadNotesKey(leadId) }),
        queryClient.invalidateQueries({ queryKey: leadDetailKey(leadId) }),
    ]);
}

export function useCreateLeadNote(leadId: string) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (body: string) => createLeadNote(leadId, body),
        onSuccess: () => invalidateNotes(queryClient, leadId),
    });
}

export function useUpdateLeadNote(leadId: string) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ noteId, body }: { noteId: string; body: string }) => updateLeadNote(leadId, noteId, body),
        onSuccess: () => invalidateNotes(queryClient, leadId),
    });
}

export function useDeleteLeadNote(leadId: string) {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (noteId: string) => deleteLeadNote(leadId, noteId),
        onSuccess: () => invalidateNotes(queryClient, leadId),
    });
}

// ── Historial real de la conversación (LEADS 05C) ───────────────────────────

/** Mismo tope que el agente aplica de su lado: una conversación real entra entera. */
export const LEAD_MESSAGES_PAGE_SIZE = 500;
export const LEAD_MESSAGES_POLL_MS = 8000;

export type LeadMessagesState = {
    messages: LeadMessage[];
    status: 'idle' | 'loading' | 'error' | 'ready';
    /** Para el estado vacío real ("no hay historial anterior") vs. aún cargando. */
    loadedOnce: boolean;
    refetch: () => void;
};

function mergeNewMessages(prev: LeadMessage[], incoming: LeadMessage[]): LeadMessage[] {
    if (incoming.length === 0) return prev;
    const seen = new Set(prev.map((m) => m.id));
    const added = incoming.filter((m) => !seen.has(m.id));
    return added.length > 0 ? [...prev, ...added] : prev;
}

/**
 * Carga el historial del Lead (acotado a `LEAD_MESSAGES_PAGE_SIZE`, igual que
 * el tope del agente) y lo actualiza solo: cada `LEAD_MESSAGES_POLL_MS` pide
 * `since=<último sent_at>` y agrega lo nuevo (dedupe por id), sin volver a
 * pedir ni redibujar todo el historial. Un error de poll no borra lo ya
 * cargado: se reintenta en el próximo intervalo.
 */
export function useLeadMessages(leadId: string): LeadMessagesState {
    const [messages, setMessages] = useState<LeadMessage[]>([]);
    const [status, setStatus] = useState<LeadMessagesState['status']>('idle');
    const [loadedOnce, setLoadedOnce] = useState(false);
    const lastSentAtRef = useRef<string | null>(null);

    const fetchAll = useCallback(async () => {
        if (!leadId) return;
        setStatus('loading');
        try {
            const page = await listLeadMessages(leadId, { limit: LEAD_MESSAGES_PAGE_SIZE });
            setMessages(page.results);
            lastSentAtRef.current = page.results.at(-1)?.sent_at ?? null;
            setStatus('ready');
        } catch {
            setStatus('error');
        } finally {
            setLoadedOnce(true);
        }
    }, [leadId]);

    const fetchNew = useCallback(async () => {
        if (!leadId || !lastSentAtRef.current) return;
        try {
            const page = await listLeadMessages(leadId, {
                since: lastSentAtRef.current,
                limit: LEAD_MESSAGES_PAGE_SIZE,
            });
            if (page.results.length === 0) return;
            setMessages((prev) => mergeNewMessages(prev, page.results));
            lastSentAtRef.current = page.results.at(-1)!.sent_at;
        } catch {
            // Silencioso: lo ya cargado se conserva, se reintenta en el próximo intervalo.
        }
    }, [leadId]);

    useEffect(() => {
        lastSentAtRef.current = null;
        setMessages([]);
        setLoadedOnce(false);
        void fetchAll();
    }, [fetchAll]);

    useEffect(() => {
        const interval = setInterval(() => void fetchNew(), LEAD_MESSAGES_POLL_MS);
        return () => clearInterval(interval);
    }, [fetchNew]);

    return { messages, status, loadedOnce, refetch: fetchAll };
}

/**
 * Responder desde el chat (MIRUBRO HUMAN MESSAGES). Sin retry propio (el
 * backend ya reintenta la entrega real de forma durable); la respuesta solo
 * confirma que se encoló, nunca que se entregó — el mensaje nuevo aparece
 * después solo, vía el polling de `useLeadMessages` ya existente.
 */
export function useSendLeadMessage(leadId: string) {
    return useMutation({
        mutationFn: (text: string) => sendLeadMessage(leadId, text),
        retry: false,
    });
}
