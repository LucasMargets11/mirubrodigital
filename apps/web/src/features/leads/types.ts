/**
 * Bandeja de Leads del agente de WhatsApp (LEADS 05A).
 *
 * Contrato de `GET /api/v1/leads/` (`LeadListSerializer`, LEADS 04A/04B.1).
 * `needs_attention` es la atención PENDIENTE calculada por el backend; el
 * frontend nunca la recalcula a partir de `needs_attention_at`.
 */

import type { AppointmentStatus } from '@/features/appointments/types';

export type LeadStatus = 'new' | 'in_progress' | 'closed';
export type LeadSource = 'whatsapp_agent';
export type LeadOutcome =
    | 'booked'
    | 'linked_customer'
    | 'not_interested'
    | 'unreachable'
    | 'duplicate'
    | 'spam'
    | 'other';

export type LeadUserRef = { id: number; display_name: string };

/** Candidato de `GET /api/v1/leads/assignees/` (solo id + nombre visible). */
export type LeadAssignee = LeadUserRef;
export type LeadCustomerRef = { id: string; display_name: string };

/** Snapshot reducido que informó el agente (solo lectura). */
export type LeadAgentSummary = {
    patient_name: string | null;
    whatsapp_profile_name: string | null;
    phone_e164: string;
    reason: string | null;
    preferred_time: string | null;
    urgency: boolean;
    agent_status: 'active' | 'closed';
    handoff_requested: boolean;
    handoff_reasons: unknown[];
    summary: string | null;
    last_message_at: string;
};

export type LeadListItem = {
    id: string;
    source: LeadSource;
    status: LeadStatus;
    outcome: LeadOutcome | null;
    created_at: string;
    updated_at: string;
    needs_attention_at: string | null;
    needs_attention: boolean;
    acknowledged_at: string | null;
    assigned_to: LeadUserRef | null;
    customer: LeadCustomerRef | null;
    agent: LeadAgentSummary | null;
    /** MIRUBRO TAKEOVER 05A: `null` sin conversación del agente; sin control todavía → `active`. */
    conversation_state: ConversationControlState | null;
};

/** Valores especiales que acepta la API en `assigned_to` / `customer`. */
export const LEADS_UNASSIGNED = 'unassigned';
export const LEADS_UNLINKED = 'unlinked';

/**
 * Filtros soportados por el backend (todos server-side). `undefined` = sin filtro.
 * `assignedTo`: id de usuario (string) o `unassigned`; `customer`: UUID o `unlinked`.
 */
export type LeadFilters = {
    status?: LeadStatus;
    source?: LeadSource;
    outcome?: LeadOutcome;
    urgency?: boolean;
    needsAttention?: boolean;
    assignedTo?: string;
    customer?: string;
    q?: string;
    limit?: number;
    offset?: number;
};

export const LEAD_STATUS_LABELS: Record<LeadStatus, string> = {
    new: 'Nuevo',
    in_progress: 'En gestión',
    closed: 'Cerrado',
};

export const LEAD_SOURCE_LABELS: Record<LeadSource, string> = {
    whatsapp_agent: 'Agente de WhatsApp',
};

export const LEAD_OUTCOME_LABELS: Record<LeadOutcome, string> = {
    booked: 'Turno agendado',
    linked_customer: 'Cliente identificado',
    not_interested: 'No interesado',
    unreachable: 'Sin respuesta',
    duplicate: 'Duplicado',
    spam: 'Spam',
    other: 'Otro',
};

/* ── Detalle (LEADS 05B) — contrato de `GET /api/v1/leads/{id}/` ─────────── */

export type LeadHandoffReasonCode =
    | 'lead_ready'
    | 'urgency'
    | 'patient_asked_human'
    | 'agent_handoff_required'
    | 'medication_question'
    | 'agent_error'
    | 'unsupported_message'
    | 'recovery_dropped';

/**
 * Snapshot completo del agente (`LeadAgentStateSerializer`). Incluye ids
 * externos y metadatos de sincronización que la UI NUNCA muestra: solo se
 * tipan los campos útiles para la operación humana.
 */
export type LeadAgentState = {
    phone_e164: string;
    patient_name: string | null;
    whatsapp_profile_name: string | null;
    reason: string | null;
    preferred_time: string | null;
    urgency: boolean;
    agent_status: 'active' | 'closed';
    handoff_requested: boolean;
    handoff_requested_at: string | null;
    handoff_reasons: unknown[];
    summary: string | null;
    opened_at: string | null;
    closed_at: string | null;
    last_message_at: string;
};

/** Referencia mínima del turno vinculado; `status` es el efectivo. */
export type LeadAppointmentRef = {
    id: string;
    start_at: string | null;
    end_at: string | null;
    status: AppointmentStatus | null;
    service_name: string | null;
};

export type LeadNote = {
    id: string;
    body: string;
    author: { id: string; name: string } | null;
    created_at: string;
    updated_at: string;
};

export type LeadActivityKind =
    | 'status_changed'
    | 'closed'
    | 'outcome_changed'
    | 'assigned'
    | 'reassigned'
    | 'unassigned'
    | 'customer_linked'
    | 'customer_changed'
    | 'customer_unlinked'
    | 'appointment_linked'
    | 'appointment_changed'
    | 'appointment_unlinked'
    | 'attention_acknowledged'
    | 'takeover_requested'
    | 'takeover_applied'
    | 'takeover_failed'
    | 'release_requested'
    | 'release_applied'
    | 'release_failed';

export type LeadChoiceRef = { value: string; label: string };
/** Referencias resueltas al leer; si el registro ya no existe llegan con `id` y el resto en null. */
export type LeadActivityUserRef = { id: number; display_name: string | null };
export type LeadActivityCustomerRef = { id: string; display_name: string | null };
export type LeadActivityRef = LeadChoiceRef | LeadActivityUserRef | LeadActivityCustomerRef | LeadAppointmentRef;

export type LeadActivity = {
    id: string;
    kind: LeadActivityKind | string;
    kind_display: string;
    occurred_at: string;
    actor: LeadUserRef | null;
    previous: LeadActivityRef | null;
    new: LeadActivityRef | null;
    metadata: Record<string, unknown>;
};

export type LeadDetail = {
    id: string;
    source: LeadSource;
    status: LeadStatus;
    outcome: LeadOutcome | null;
    assigned_to: LeadUserRef | null;
    customer: LeadCustomerRef | null;
    appointment: LeadAppointmentRef | null;
    needs_attention_at: string | null;
    needs_attention: boolean;
    acknowledged_at: string | null;
    acknowledged_by: LeadUserRef | null;
    closed_at: string | null;
    closed_by: LeadUserRef | null;
    created_at: string;
    updated_at: string;
    agent_state: LeadAgentState | null;
    conversation_control: LeadConversationControl | null;
    notes: LeadNote[];
    activity: LeadActivity[];
};

/** PATCH CRM: el backend rechaza cualquier otra clave. */
export type LeadUpdatePayload = {
    status?: LeadStatus;
    outcome?: LeadOutcome;
    assigned_to?: number | null;
    customer?: string | null;
    appointment?: string | null;
};

export const LEAD_NOTE_MAX_LENGTH = 2000;

export const LEAD_HANDOFF_REASON_LABELS: Record<LeadHandoffReasonCode, string> = {
    lead_ready: 'La consulta está lista para que la tome el equipo',
    urgency: 'Caso urgente',
    patient_asked_human: 'Pidió hablar con una persona',
    agent_handoff_required: 'El agente necesita que intervenga una persona',
    medication_question: 'Consulta sobre medicación',
    agent_error: 'El agente tuvo un problema',
    unsupported_message: 'Envió un mensaje que el agente no puede procesar',
    recovery_dropped: 'Se perdió parte de la conversación',
};

/* ── Control humano de la conversación (MIRUBRO TAKEOVER 05B) ──────────────
 * Contrato de `serialize_conversation_control` (backend 05A). `taken`/`active`
 * solo llegan cuando el agente confirmó: la UI nunca los adelanta.
 */

export type ConversationControlState = 'active' | 'takeover_pending' | 'taken' | 'release_pending' | 'error';
export type ConversationCommandAction = 'takeover' | 'release';

export type LeadConversationControl = {
    /** Se puede pedir takeover/release (integración encendida y conversación del agente válida). */
    available: boolean;
    state: ConversationControlState;
    command_version: number;
    /** Acción del último comando pedido: decide qué se reintenta desde `error`. */
    last_action: ConversationCommandAction | null;
    taken_at: string | null;
    taken_by: LeadUserRef | null;
    released_at: string | null;
    last_error_code: string | null;
};

/** 202 (comando nuevo) o 200 (idempotente: ya hecho o en curso). */
export type ConversationCommandResponse = {
    ok: true;
    state: ConversationControlState;
    command_version: number;
};

/* ── Historial real de la conversación (LEADS 05C) ──────────────────────────
 * Contrato de `GET /api/v1/leads/{id}/messages/` (`LeadMessageSerializer`).
 * `role` dice de qué lado vino (paciente/izquierda vs agente/derecha);
 * `sender` distingue, del lado del agente, si lo escribió el bot o una
 * persona de recepción (mensaje humano por takeover). `status` solo tiene
 * valor para salientes y únicamente cuando Meta confirmó un estado.
 */

export type LeadMessageRole = 'user' | 'assistant';
export type LeadMessageSender = 'patient' | 'bot' | 'staff';
export type LeadMessageStatus = 'sent' | 'delivered' | 'read' | 'failed';

/** Solo para mensajes `sender=staff` ya sincronizados; `null` en cualquier otro caso. */
export type LeadMessageAuthor = { id: number | null; display_name: string };

export type LeadMessage = {
    id: string;
    role: LeadMessageRole;
    sender: LeadMessageSender;
    text: string;
    sent_at: string;
    status: LeadMessageStatus | null;
    authored_by: LeadMessageAuthor | null;
};

export const LEAD_MESSAGE_SENDER_LABELS: Record<LeadMessageSender, string> = {
    patient: 'Paciente',
    bot: 'Bot',
    staff: 'Recepción',
};

export const LEAD_MESSAGE_STATUS_LABELS: Record<LeadMessageStatus, string> = {
    sent: 'Enviado',
    delivered: 'Entregado',
    read: 'Leído',
    // Meta confirmó que no se entregó (o lo rechazó): nunca le llegó al paciente.
    failed: 'No enviado',
};

/** Saliente sin ningún status de Meta todavía: no hay evidencia, nunca se asume "enviado". */
export const LEAD_MESSAGE_STATUS_UNKNOWN_LABEL = 'Estado desconocido';

/* ── Responder desde el chat (MIRUBRO HUMAN MESSAGES) ───────────────────────
 * Contrato de `POST /api/v1/leads/{id}/messages/`. La respuesta solo confirma
 * que se aceptó para envío (outbox local): NUNCA dice "enviado". El estado
 * real (sent/delivered/read/failed) llega después, solo, por el polling de
 * `LeadMessage` ya existente (LEADS 05C).
 */
export const LEAD_MESSAGE_TEXT_MAX_LENGTH = 4096;

export type SendLeadMessageResponse = {
    ok: true;
    status: 'queued_locally';
    id: string;
};
