'use client';

import { ReceptionValidityExtension, extendableReceptionSubscription } from '@/components/admin/reception-validity-extension';
import { SectionCard } from '@/components/admin/section-card';
import { StatusBadge } from '@/components/admin/status-badge';
import { AIUsageSummaryView, aiUsageTierLabel } from '@/features/reception/ai-usage-summary-panel';
import { useAdminAIUsage } from '@/features/reception/hooks';
import type { AdminAIUsageOverview } from '@/features/reception/types';
import { formatDateFromTimestampAR, formatDateTimeAR } from '@/lib/dates';
import { formatNumber } from '@/lib/format';

const UNKNOWN = 'Sin datos';

/** Códigos de diagnóstico de PROD-02E3B; un código no listado se muestra tal cual. */
const DIAGNOSIS_LABELS: Record<string, string> = {
    ok: 'Habilitado',
    no_ai_subscription: 'Sin suscripción de IA',
    subscription_canceled: 'Suscripción cancelada',
    subscription_suspended: 'Suscripción suspendida',
    past_due_grace_expired: 'Pago vencido, fuera de gracia',
    subscription_not_active: 'Suscripción no activa',
    benefit_not_started: 'Bonificación aún no iniciada',
    benefit_expired: 'Bonificación vencida',
    canceled_at_period_end: 'Cancelada al fin del período',
    business_not_active: 'Negocio inactivo',
    invalid_tier: 'Tier inválido',
    custom_policy_missing: 'Sin política personalizada',
    custom_policy_revoked: 'Política personalizada revocada',
    custom_policy_not_started: 'Política personalizada aún no vigente',
    custom_policy_expired: 'Política personalizada vencida',
    usage_policy_undefined: 'Política de uso no definida',
    quota_exhausted: 'Cupo agotado',
    ambiguous_ai_source: 'Más de una fuente de IA',
    reception_kill_switch_disabled: 'Recepcionista deshabilitada globalmente',
    metering_disabled: 'Medición deshabilitada',
    resolution_error: 'No se pudo resolver el consumo',
    usage_unavailable: 'Consumo no disponible',
};

const POLICY_LABELS: Record<string, string> = { catalog: 'Catálogo (cupo fijo)', custom: 'Personalizada' };

function Field({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div>
            <dt className="text-xs uppercase tracking-wide text-slate-400">{label}</dt>
            <dd className="text-sm text-slate-700">{children}</dd>
        </div>
    );
}

function dateOrUnknown(value: string | null | undefined) {
    return value ? formatDateFromTimestampAR(value) : UNKNOWN;
}

function AdminDetails({ overview }: { overview: AdminAIUsageOverview }) {
    const { diagnosis, source_subscription: sub, summary } = overview;
    const ok = diagnosis.code === 'ok';
    const tier = aiUsageTierLabel(sub?.usage_tier ?? summary?.source?.usage_tier);
    const policy = summary?.source?.policy_kind;
    const overage = summary?.overage;

    return (
        <dl className="grid gap-3 sm:grid-cols-2">
            <Field label="Diagnóstico">
                <StatusBadge
                    label={DIAGNOSIS_LABELS[diagnosis.code] ?? diagnosis.code}
                    colorClass={ok ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-800'}
                />{' '}
                <code className="text-xs text-slate-400">{diagnosis.code}</code>
            </Field>
            <Field label="Fuente de consumo">
                {sub ? `${sub.plan_code}${tier ? ` · ${tier}` : ''}` : UNKNOWN}
            </Field>
            <Field label="Suscripción">
                {sub ? `${sub.status}${sub.complimentary ? ' · bonificada' : ''}${sub.cancel_at_period_end ? ' · cancela al fin del período' : ''}` : UNKNOWN}
            </Field>
            <Field label="Vigencia de la suscripción">
                {sub ? `${dateOrUnknown(sub.current_period_start)} al ${dateOrUnknown(sub.current_period_end)}` : UNKNOWN}
            </Field>
            <Field label="Política">{policy ? POLICY_LABELS[policy] ?? policy : UNKNOWN}</Field>
            <Field label="Tope del período">
                {summary?.hard_cap
                    ? `${formatNumber(summary.hard_cap.max_sessions)} sesiones (quedan ${formatNumber(summary.hard_cap.remaining_sessions)})`
                    : UNKNOWN}
            </Field>
            <Field label="Excedentes">
                {overage ? (overage.enabled ? `Habilitados (hasta ${formatNumber(overage.max_sessions)} sesiones)` : 'No habilitados') : UNKNOWN}
            </Field>
            <Field label="Evaluado">{formatDateTimeAR(overview.evaluated_at)}</Field>
        </dl>
    );
}

/**
 * PROD-08D — Consumo comercial de IA del cliente. Reutiliza la presentación
 * de `AIUsageSummaryPanel` con el `summary` administrativo: nunca consulta
 * `GET /api/v1/ai-usage/` (endpoint del comercio). Solo lectura, salvo la
 * acción «Extender vigencia» (PROD-09D2): solo superadmin y solo sobre una
 * bonificación manual de Recepcionista identificada por la fuente comercial.
 */
export function AdminAIUsageSection({ businessId, businessName = '', canExtendValidity = false }: {
    businessId: number;
    businessName?: string;
    /** Solo superadmin (sesión de Platform Admin); el backend vuelve a verificarlo. */
    canExtendValidity?: boolean;
}) {
    const query = useAdminAIUsage(businessId);
    const extendable = canExtendValidity ? extendableReceptionSubscription(query.data) : null;

    return (
        <SectionCard
            title="Consumo comercial de IA"
            description="Sesiones de IA del plan del cliente. Es autorización comercial: no indica que el agente esté conectado."
        >
            <div className="space-y-4">
                <AIUsageSummaryView
                    audience="platform_admin"
                    variant="full"
                    state={{
                        isLoading: query.isLoading,
                        isError: query.isError,
                        error: query.error,
                        data: query.data?.summary ?? null,
                    }}
                />
                {query.data ? <AdminDetails overview={query.data} /> : null}
                {extendable ? (
                    <ReceptionValidityExtension
                        key={`${businessId}:${extendable.id}`}
                        businessId={businessId}
                        businessName={businessName}
                        subscription={extendable}
                    />
                ) : null}
            </div>
        </SectionCard>
    );
}
