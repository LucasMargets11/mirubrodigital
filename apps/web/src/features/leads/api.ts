import { apiDelete, apiGet, apiPatch, apiPost } from '@/lib/api/client';
import type { PaginatedResponse } from '@/types/api';

import type {
    ConversationCommandResponse,
    LeadAssignee,
    LeadDetail,
    LeadFilters,
    LeadListItem,
    LeadMessage,
    LeadNote,
    LeadUpdatePayload,
    SendLeadMessageResponse,
} from './types';

/** Query string de la bandeja. Sin `ordering`: el backend aplica `priority` por defecto. */
export function buildLeadQuery(filters: LeadFilters): string {
    const params = new URLSearchParams();
    if (filters.status) params.set('status', filters.status);
    if (filters.source) params.set('source', filters.source);
    if (filters.outcome) params.set('outcome', filters.outcome);
    if (typeof filters.urgency === 'boolean') params.set('urgency', String(filters.urgency));
    if (typeof filters.needsAttention === 'boolean') params.set('needs_attention', String(filters.needsAttention));
    if (filters.assignedTo) params.set('assigned_to', filters.assignedTo);
    if (filters.customer) params.set('customer', filters.customer);
    if (filters.q) params.set('q', filters.q);
    if (typeof filters.limit === 'number') params.set('limit', String(filters.limit));
    if (typeof filters.offset === 'number') params.set('offset', String(filters.offset));
    const query = params.toString();
    return query ? `?${query}` : '';
}

export function listLeads(filters: LeadFilters = {}) {
    return apiGet<PaginatedResponse<LeadListItem>>(`/api/v1/leads/${buildLeadQuery(filters)}`);
}

// ── Detalle (LEADS 05B) ──────────────────────────────────────────────────────

export function getLead(id: string) {
    return apiGet<LeadDetail>(`/api/v1/leads/${id}/`);
}

/** PATCH CRM; responde el detalle completo (con `activity` actualizada). */
export function updateLead(id: string, payload: LeadUpdatePayload) {
    return apiPatch<LeadDetail>(`/api/v1/leads/${id}/`, payload);
}

/**
 * Personas asignables del Business actual (LEADS 05B.1): misma regla que
 * valida el PATCH de `assigned_to`. Lista corta, sin paginar, ordenada por nombre.
 */
export function listLeadAssignees() {
    return apiGet<LeadAssignee[]>('/api/v1/leads/assignees/');
}

/** Idempotente: si ya estaba reconocida responde 200 con el detalle sin cambios. */
export function acknowledgeLeadAttention(id: string) {
    return apiPost<LeadDetail>(`/api/v1/leads/${id}/acknowledge-attention/`);
}

export function listLeadNotes(leadId: string, params: { limit?: number; offset?: number } = {}) {
    const searchParams = new URLSearchParams();
    if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
    if (params.offset !== undefined) searchParams.set('offset', String(params.offset));
    const query = searchParams.toString();
    return apiGet<PaginatedResponse<LeadNote>>(`/api/v1/leads/${leadId}/notes/${query ? `?${query}` : ''}`);
}

export function createLeadNote(leadId: string, body: string) {
    return apiPost<LeadNote>(`/api/v1/leads/${leadId}/notes/`, { body });
}

export function updateLeadNote(leadId: string, noteId: string, body: string) {
    return apiPatch<LeadNote>(`/api/v1/leads/${leadId}/notes/${noteId}/`, { body });
}

export function deleteLeadNote(leadId: string, noteId: string) {
    return apiDelete<void>(`/api/v1/leads/${leadId}/notes/${noteId}/`);
}

// ── Historial real de la conversación (LEADS 05C) ───────────────────────────

/**
 * Orden cronológico ascendente. `since` (ISO-8601 con zona) trae solo lo
 * posterior: así el panel actualiza sin volver a pedir todo el historial.
 */
export function listLeadMessages(
    leadId: string,
    params: { limit?: number; offset?: number; since?: string } = {},
) {
    const searchParams = new URLSearchParams();
    if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
    if (params.offset !== undefined) searchParams.set('offset', String(params.offset));
    if (params.since) searchParams.set('since', params.since);
    const query = searchParams.toString();
    return apiGet<PaginatedResponse<LeadMessage>>(`/api/v1/leads/${leadId}/messages/${query ? `?${query}` : ''}`);
}

/**
 * Responder desde el chat (MIRUBRO HUMAN MESSAGES): encola el mensaje hacia
 * el paciente. Responde de inmediato ("aceptado", nunca "enviado"); el
 * resultado real llega por el polling de `listLeadMessages`.
 */
export function sendLeadMessage(leadId: string, text: string) {
    return apiPost<SendLeadMessageResponse>(`/api/v1/leads/${leadId}/messages/`, { text });
}

// ── Control humano de la conversación (MIRUBRO TAKEOVER 05B) ────────────────

/**
 * Pide tomar la conversación (pausar el bot). Sin body. Responde el estado
 * inicial (`takeover_pending`, o el actual si ya estaba hecho/en curso); la
 * entrega al agente es asíncrona y la reintenta el backend.
 */
export function takeoverLead(id: string) {
    return apiPost<ConversationCommandResponse>(`/api/v1/leads/${id}/takeover/`);
}

/** Pide devolver la conversación al bot. Mismo contrato que `takeoverLead`. */
export function releaseLead(id: string) {
    return apiPost<ConversationCommandResponse>(`/api/v1/leads/${id}/release/`);
}
