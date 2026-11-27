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
    | 'unavailable';

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
    version: number;
    missing_for_ready: string[];
    created_at: string;
    updated_at: string;
};

export type ReceptionistConfigResponse = { config: ReceptionistConfig | null };

export type ReceptionistConfigPatch = Partial<ReceptionistConfigContent> & {
    status?: ReceptionistConfigStatus;
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
