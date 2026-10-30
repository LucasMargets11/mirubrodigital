import { ApiError } from '@/lib/api/client';

export const PROPOSAL_TAKEOVER_REQUIRED = 'Para enviar una propuesta primero tenés que tomar la conversación.';
export const PROPOSAL_SLOT_UNAVAILABLE = 'Ese horario ya no está disponible. Elegí otro.';

export function appointmentProposalErrorCode(error: unknown): string | null {
    if (!(error instanceof ApiError) || !error.payload || typeof error.payload !== 'object') return null;
    const payload = error.payload as Record<string, unknown>;
    return typeof payload.code === 'string' ? payload.code : null;
}

export function appointmentProposalConfirmationError(error: unknown): string {
    const code = appointmentProposalErrorCode(error);
    if (code === 'slot_unavailable') return 'Ese horario ya no está disponible. Elegí otro horario para continuar.';
    if (code === 'proposal_expired') return 'La propuesta venció. Proponé otro horario.';
    if (code === 'proposal_superseded') return 'La propuesta fue reemplazada. Actualizamos la información.';
    if (code === 'proposal_delivery_failed') return 'No se pudo enviar esta propuesta. Proponé otro horario.';
    if (code === 'lead_already_has_appointment') return 'El lead ya tiene un turno vinculado. Actualizamos la información.';
    return resolveLeadApiError(error, 'No pudimos confirmar el turno. Intentá nuevamente.');
}

export function appointmentProposalDeliveryError(code: string | null): string {
    if (code === 'conversation_not_taken') return PROPOSAL_TAKEOVER_REQUIRED;
    if (code === 'conversation_not_found' || code === 'conversation_unavailable') return 'La conversación ya no está disponible.';
    if (code === 'outside_service_window') return 'La ventana de atención de WhatsApp está cerrada. Esperá un nuevo mensaje del paciente.';
    if (code === 'human_messages_disabled') return 'El envío de mensajes al paciente está deshabilitado.';
    if (code === 'message_conflict') return 'El agente rechazó el envío por un conflicto de mensaje. Intentá otra propuesta.';
    if (code === 'invalid_payload') return 'El agente no pudo procesar la propuesta. Revisá la integración.';
    if (code === 'timeout' || code === 'network_error') return 'No pudimos comunicarnos con el agente.';
    if (code && CONVERSATION_CONTROL_ERROR_MESSAGES[code]) return CONVERSATION_CONTROL_ERROR_MESSAGES[code];
    return 'No se pudo completar el envío. Intentá otra propuesta o revisá la integración.';
}

/**
 * Primer mensaje legible de un error de la API de Leads: `detail`, luego el
 * primer error de campo (`{status: '...'}`, `{outcome: ['...']}`,
 * `{non_field_errors: [...]}`). Las reglas viven en el backend: la UI solo
 * muestra lo que responde.
 */
export function resolveLeadApiError(error: unknown, fallback: string): string {
    if (error instanceof ApiError && error.payload && typeof error.payload === 'object') {
        const payload = error.payload as Record<string, unknown>;
        if (typeof payload.detail === 'string') return payload.detail;
        for (const value of Object.values(payload)) {
            if (typeof value === 'string' && value) return value;
            if (Array.isArray(value) && typeof value[0] === 'string') return value[0];
        }
    }
    if (error instanceof ApiError && error.status === 403) {
        return 'No tenés permiso para realizar esta acción.';
    }
    return fallback;
}

// ── Control humano de la conversación (MIRUBRO TAKEOVER 05B) ────────────────

export const CONVERSATION_CONTROL_ERROR_FALLBACK = 'No pudimos cambiar el control de esta conversación.';

const INTEGRATION_REVIEW = 'La integración con el bot necesita revisión.';

/**
 * `last_error_code` del control (códigos del cliente HTTP o del agente,
 * backend 05A) → texto para recepción. Nunca se muestra el código crudo.
 */
const CONVERSATION_CONTROL_ERROR_MESSAGES: Record<string, string> = {
    network_error: 'No pudimos comunicarnos con el bot.',
    timeout: 'El bot tardó demasiado en responder.',
    invalid_signature: INTEGRATION_REVIEW,
    http_401: INTEGRATION_REVIEW,
    http_403: INTEGRATION_REVIEW,
    tls_required: INTEGRATION_REVIEW,
    client_not_configured: INTEGRATION_REVIEW,
    takeover_disabled: 'El control del bot está deshabilitado.',
    conversation_not_found: 'El bot ya no reconoce esta conversación.',
    version_conflict: 'El estado de la conversación está desincronizado.',
    version_regression: 'El estado de la conversación está desincronizado.',
    business_mismatch: 'La configuración de esta conversación no coincide con el negocio.',
};

export function conversationControlErrorMessage(code: string | null | undefined): string {
    return (code && CONVERSATION_CONTROL_ERROR_MESSAGES[code]) || CONVERSATION_CONTROL_ERROR_FALLBACK;
}

export type ConversationCommandFeedback = { tone: 'info' | 'error'; message: string };

/**
 * Error del POST takeover/release. 409 (acción opuesta en curso) y 503
 * (integración apagada) no son fallas del usuario: se informan como cambio
 * de estado y se refresca el Lead (lo hace la mutation).
 */
export function conversationCommandRequestFeedback(error: unknown): ConversationCommandFeedback {
    if (error instanceof ApiError && error.status === 409) {
        return { tone: 'info', message: 'El estado de la conversación cambió. Actualizamos la información.' };
    }
    if (error instanceof ApiError && error.status === 503) {
        return { tone: 'error', message: 'El control del bot no está disponible en este momento.' };
    }
    if (error instanceof ApiError && error.status === 400) {
        return { tone: 'error', message: 'Esta conversación no admite el control del bot.' };
    }
    if (error instanceof ApiError && error.status === 403) {
        return { tone: 'error', message: 'No tenés permiso para realizar esta acción.' };
    }
    if (error instanceof ApiError && error.status === 404) {
        return { tone: 'error', message: 'No encontramos este lead.' };
    }
    return { tone: 'error', message: `${CONVERSATION_CONTROL_ERROR_FALLBACK} Intentá nuevamente.` };
}

// ── Responder desde el chat (MIRUBRO HUMAN MESSAGES) ────────────────────────

/**
 * Error del POST de un mensaje nuevo. Esta respuesta es solo la aceptación
 * LOCAL (encolado); nunca confirma el envío real al paciente, así que un
 * error acá siempre es "no se aceptó el mensaje", nunca "no se entregó".
 */
export function sendLeadMessageErrorMessage(error: unknown): string {
    if (error instanceof ApiError && error.status === 503) {
        return 'El envío de mensajes no está habilitado en este momento.';
    }
    if (error instanceof ApiError && error.status === 400) {
        const payload = error.payload as Record<string, unknown> | undefined;
        if (payload && typeof payload === 'object' && 'code' in payload) {
            return 'Esta conversación no admite el envío de mensajes desde acá.';
        }
        return resolveLeadApiError(error, 'Revisá el mensaje e intentá nuevamente.');
    }
    if (error instanceof ApiError && error.status === 403) {
        return 'No tenés permiso para enviar mensajes en este lead.';
    }
    if (error instanceof ApiError && error.status === 404) {
        return 'No encontramos este lead.';
    }
    return 'No pudimos enviar el mensaje. Intentá nuevamente.';
}
