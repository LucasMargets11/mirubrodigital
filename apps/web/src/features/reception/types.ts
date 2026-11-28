/**
 * PROD-02G1 — Contrato v1 de `GET /api/v1/ai-usage/` (PROD-02E3A), solo lectura.
 * Neutro de producto: describe la única fuente de IA del negocio.
 */

export type AIUsageStatus =
    | 'available'
    | 'exhausted'
    | 'policy_not_configured'
    | 'suspended'
    | 'ambiguous_source'
    | 'unavailable'
    /** Solo Platform Admin: el comercio recibe 403 `ai_service_not_contracted`. */
    | 'not_contracted';

export type AIUsageSource = {
    product: 'reception' | 'appointments_ai';
    service_type: string;
    plan_code: string;
    usage_tier: string | null;
    policy_kind: 'custom' | 'catalog';
};

export type AIUsageSummary = {
    contract_version: number;
    evaluated_at: string;
    status: AIUsageStatus;
    reason: string | null;
    can_start_new_session: boolean;
    unit: string;
    source: AIUsageSource | null;
    period: { start: string; end: string } | null;
    sessions: { included: number; used: number; available_included: number } | null;
    hard_cap: { max_sessions: number; remaining_sessions: number } | null;
    overage: {
        enabled: boolean;
        unit_price: string | number | null;
        spend_limit: string | number | null;
        max_sessions: number;
        used_sessions: number;
        amount: string | number | null;
        currency: string;
    } | null;
    scheduled_change: { included_sessions: number; effective_at: string } | null;
};

/**
 * PROD-08D — `GET /api/v1/platform-admin/clients/{id}/ai-usage/` (PROD-02E3B).
 * `summary` es el mismo contrato del comercio; `null` si no pudo resolverse.
 */
export type AdminAIUsageOverview = {
    business_id: number;
    evaluated_at: string;
    summary: AIUsageSummary | null;
    source_subscription: {
        id: string;
        product: string;
        service_type: string;
        plan_code: string;
        usage_tier: string | null;
        status: string;
        provider: string;
        billing_cycle: string | null;
        complimentary: boolean;
        current_period_start: string | null;
        current_period_end: string | null;
        grace_until: string | null;
        cancel_at_period_end: boolean;
        canceled_at: string | null;
    } | null;
    diagnosis: { code: string; subscription_id: string | null; candidates: unknown[] };
    scope: string;
};

/** Conteo que el backend informa como `null` cuando no hay datos (nunca 0). */
type Count = number | null;
type TokenBlock = { total: number | null; reported: number; unknown: number };

/**
 * PROD-08D — `GET /api/v1/platform-admin/clients/{id}/operational-metrics/`
 * (PROD-02E4C/02E4D). Bloques independientes, nunca sumables entre sí.
 */
export type OperationalMetrics = {
    contract_version: number;
    business_id: number;
    period: { timezone: string; date_from: string; date_to: string; days: number };
    openai_activity: {
        executions: number;
        by_status: Record<string, number>;
        tokens: { input: TokenBlock; output: TokenBlock; cached_input: TokenBlock };
        latency_ms: { reported: number; average: number | null; p95: number | null; p95_min_samples: number };
    };
    openai_costs: {
        currency: string;
        kind: 'estimated';
        estimated_total: string;
        complete: boolean;
        costed_executions: number;
        uncosted_executions: number;
        uncosted_reasons: Record<string, number>;
    };
    whatsapp: {
        available: boolean;
        totals: { messages: Count; inbound: Count; outbound: Count; ai_generated: null; automated_non_ai: null };
        by_sender: { patient: Count; bot: Count; staff: Count };
        outbound_status: { sent: Count; delivered: Count; read: Count; failed: Count; unknown: Count };
        conversations: { with_activity: Count; leads_with_activity: Count };
        handoffs: { requested: Count; bot_paused_for_reception: Count; takeovers_applied: Count; releases_applied: Count };
        staff_messages: { requested: number; queued_in_agent: number; pending: number; failed: number };
        coverage: { has_agent_channel: boolean; sync_observed: boolean; leads_at_message_cap: number };
    };
};

/**
 * PROD-08B — Contrato de `ReceptionistConfig` (PROD-03A/03B). Los 13 campos
 * de contenido + `status`; `version` es la del bloqueo optimista. `ready`
 * significa configuración completa, nunca agente conectado.
 */
export type ReceptionistConfigStatus = 'draft' | 'ready';
export type ReceptionistTone = 'warm' | 'professional' | 'formal';
export type ReceptionistLanguage = 'es-AR' | 'es';
export type ReceptionistService = { name: string; description?: string };
export type ReceptionistFaq = { question: string; answer: string };

export type ReceptionistConfigContent = {
    assistant_name: string;
    business_category: string;
    business_description: string;
    custom_instructions: string;
    tone: ReceptionistTone;
    language: ReceptionistLanguage;
    welcome_message: string;
    operational_info: string;
    business_hours: string;
    services: ReceptionistService[];
    reference_info: string;
    faqs: ReceptionistFaq[];
    handoff_rules: string;
};

export type ReceptionistConfigField = keyof ReceptionistConfigContent;

export type ReceptionistConfig = ReceptionistConfigContent & {
    id: string;
    status: ReceptionistConfigStatus;
    /**
     * PROD-09C1/09C3 — Control operativo, independiente de `status`. Lo
     * escribe solo Platform Admin. Ausente o no booleano = estado desconocido
     * (nunca se asume habilitada).
     */
    automatic_attention_enabled?: boolean;
    version: number;
    missing_for_ready: string[];
    created_at: string;
    updated_at: string;
};

export type ReceptionistConfigResponse = { config: ReceptionistConfig | null };

export type ReceptionistConfigPatch = Partial<ReceptionistConfigContent> & {
    status?: ReceptionistConfigStatus;
    /** Solo Platform Admin (el comercio recibe 400 `protected_fields`). */
    automatic_attention_enabled?: boolean;
    expected_version: number;
};

/** Límites del modelo (`apps/leads/models.py`); el backend vuelve a validarlos. */
export const RECEPTIONIST_TEXT_LIMITS = {
    assistant_name: 80,
    business_category: 80,
    business_description: 1000,
    custom_instructions: 4000,
    welcome_message: 500,
    operational_info: 2000,
    business_hours: 1000,
    reference_info: 4000,
    handoff_rules: 2000,
} as const;

export const RECEPTIONIST_LIST_LIMITS = {
    services: { maxItems: 30, name: 120, description: 500 },
    faqs: { maxItems: 30, question: 300, answer: 1000 },
} as const;

/**
 * PROD-08E2 — `GET /api/v1/platform-admin/clients/{id}/whatsapp-connections/`
 * (PROD-08E1). Estado LOCAL de Mi Rubro: nunca conectividad real con Meta.
 * `local_status` es la fuente de verdad; un valor no listado es desconocido.
 */
export type WhatsAppLocalStatus =
    | 'credential_ready'
    | 'channel_not_active'
    | 'whatsapp_authorization_missing'
    | 'whatsapp_authorization_owner_mismatch'
    | 'whatsapp_authorization_revoked'
    | 'whatsapp_authorization_invalid'
    | 'whatsapp_authorization_expired'
    | 'whatsapp_waba_missing'
    | 'agent_instance_disabled';

export type AdminWhatsAppChannel = {
    id: string;
    provider: string;
    phone_number_id: string;
    waba_id: string | null;
    is_active: boolean;
    created_at: string | null;
    deactivated_at: string | null;
    agent_instance: { external_id: string; name: string; is_enabled: boolean; disabled_at: string | null };
    authorization: {
        id: string;
        kind: 'business' | 'platform' | string;
        owned_by_this_business: boolean | null;
        status: string;
        expired: boolean;
        expires_at: string | null;
        revoked_at: string | null;
        created_at: string | null;
        updated_at: string | null;
    } | null;
    local_status: WhatsAppLocalStatus | string;
};

export type AdminWhatsAppConnections = {
    contract_version: number;
    business_id: number;
    evaluated_at: string;
    channels: AdminWhatsAppChannel[];
    external_verification: { performed: boolean; meta_connectivity: string; detail: string };
};
