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
