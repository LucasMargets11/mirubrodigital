"use client";

import { ApiError } from '@/lib/api/client';
import { formatDateFromTimestampAR } from '@/lib/dates';
import { formatNumber } from '@/lib/format';

import { useAIUsageSummary } from './hooks';
import type { AIUsageSummary } from './types';

const TIER_LABELS: Record<string, string> = {
    reception_300: 'Recepcionista 300',
    reception_1500: 'Recepcionista 1.500',
    reception_3000: 'Recepcionista 3.000',
    reception_custom: 'Recepcionista personalizado',
};

type Message = { title: string; description: string };
type Audience = 'business' | 'platform_admin';

const STATUS_MESSAGES: Record<Exclude<AIUsageSummary['status'], 'available'>, Message> = {
    exhausted: {
        title: 'Cupo del período agotado',
        description: 'El agente no inicia conversaciones nuevas hasta que empiece el próximo período.',
    },
    suspended: {
        title: 'Recepcionista IA sin acceso vigente',
        description: 'El servicio está suspendido o fuera de su período bonificado. Revisá tu plan o contactá a soporte.',
    },
    policy_not_configured: {
        title: 'Cupo pendiente de configuración',
        description: 'Tu acuerdo todavía no tiene un cupo vigente. Contactá a soporte.',
    },
    ambiguous_source: {
        title: 'Configuración de IA a revisar',
        description: 'Hay más de un servicio de IA asociado a tu negocio. Contactá a soporte.',
    },
    unavailable: {
        title: 'Consumo no disponible',
        description: 'La medición del consumo no está disponible en este momento.',
    },
    not_contracted: {
        title: 'Sin servicio de IA contratado',
        description: 'Tu negocio no tiene Recepcionista IA vigente.',
    },
};

/** PROD-08D — Platform Admin: mismos estados, textos sobre el cliente (no «tu plan»). */
const ADMIN_DESCRIPTIONS: Partial<Record<keyof typeof STATUS_MESSAGES, string>> = {
    suspended: 'El servicio está suspendido o fuera de su período bonificado.',
    policy_not_configured: 'El acuerdo del cliente no tiene un cupo vigente.',
    ambiguous_source: 'El cliente tiene más de un servicio de IA asociado.',
    not_contracted: 'El cliente no tiene un servicio de IA contratado.',
};

function statusMessage(status: keyof typeof STATUS_MESSAGES, audience: Audience): Message {
    const base = STATUS_MESSAGES[status] ?? STATUS_MESSAGES.unavailable;
    const description = audience === 'platform_admin' ? ADMIN_DESCRIPTIONS[status] : undefined;
    return description ? { ...base, description } : base;
}

export function aiUsageTierLabel(tier: string | null | undefined): string | null {
    if (!tier) return null;
    return TIER_LABELS[tier] ?? null;
}

function tierLabel(summary: AIUsageSummary): string | null {
    return aiUsageTierLabel(summary.source?.usage_tier);
}

function errorMessage(error: unknown, audience: Audience): Message {
    if (error instanceof ApiError && error.status === 403 && audience === 'platform_admin') {
        return { title: 'Sin acceso', description: 'Tu rol de Platform Admin no puede ver el consumo de IA.' };
    }
    if (error instanceof ApiError && error.status === 403) {
        const code = (error.payload as { code?: string } | undefined)?.code;
        if (code === 'ai_service_not_contracted') {
            return {
                title: 'Sin servicio de IA contratado',
                description: 'Tu negocio no tiene Recepcionista IA vigente.',
            };
        }
        return { title: 'Sin acceso', description: 'Tu rol no puede ver el consumo de IA.' };
    }
    return { title: 'No pudimos cargar el consumo', description: 'Intentá nuevamente en unos minutos.' };
}

type Props = {
    /** `compact`: resumen para Inicio; `full`: detalle del período en Consumo. */
    variant?: 'compact' | 'full';
};

/**
 * Consumo comercial de IA (contrato v1 de `GET /api/v1/ai-usage/`). Solo
 * lectura: nunca inicia sesiones ni modifica cupos.
 */
export function AIUsageSummaryPanel({ variant = 'full' }: Props) {
    const query = useAIUsageSummary();
    return <AIUsageSummaryView state={query} variant={variant} />;
}

export type AIUsageSummaryState = {
    isLoading: boolean;
    isError: boolean;
    data?: AIUsageSummary | null;
    error: unknown;
};

/**
 * PROD-08D — La misma presentación alimentada por quien llama: Platform Admin
 * le pasa el `summary` de su endpoint y nunca consulta el del comercio.
 */
export function AIUsageSummaryView({
    state: query,
    variant = 'full',
    audience = 'business',
}: Props & { state: AIUsageSummaryState; audience?: Audience }) {
    if (query.isLoading) {
        return (
            <section aria-busy="true" className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <p className="text-sm text-slate-500">Cargando consumo…</p>
            </section>
        );
    }

    if (query.isError || !query.data) {
        const message = errorMessage(query.error, audience);
        return (
            <section role="status" className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <h2 className="text-sm font-semibold text-slate-800">{message.title}</h2>
                <p className="text-sm text-slate-500">{message.description}</p>
            </section>
        );
    }

    const summary = query.data;
    const tier = tierLabel(summary);

    if (summary.status !== 'available' && summary.status !== 'exhausted') {
        const message = statusMessage(summary.status, audience);
        return (
            <section role="status" className="rounded-2xl border border-amber-200 bg-amber-50 p-4 shadow-sm">
                <h2 className="text-sm font-semibold text-amber-900">{message.title}</h2>
                <p className="text-sm text-amber-800">{message.description}</p>
                {tier ? <p className="mt-1 text-xs text-amber-700">Plan: {tier}</p> : null}
            </section>
        );
    }

    // Sin `sessions` (p. ej. tope alcanzado sin lectura) no hay números: nunca 0.
    const sessions = summary.sessions;
    const percent = sessions && sessions.included > 0
        ? Math.min(100, Math.round((sessions.used / sessions.included) * 100))
        : 0;

    return (
        <section aria-labelledby="ai-usage-title" className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <header className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 id="ai-usage-title" className="text-sm font-semibold text-slate-800">Conversaciones del período</h2>
                {tier ? <span className="text-xs text-slate-500">{tier}</span> : null}
            </header>
            {sessions ? (
                <p className="text-2xl font-semibold text-slate-900">
                    {formatNumber(sessions.used)}{' '}
                    <span className="text-base font-normal text-slate-500">de {formatNumber(sessions.included)}</span>
                </p>
            ) : (
                <p className="text-sm text-slate-500">Sin datos de sesiones del período.</p>
            )}
            {sessions ? (
                <div
                    role="progressbar"
                    aria-label="Conversaciones usadas"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={percent}
                    className="h-2 w-full overflow-hidden rounded-full bg-slate-100"
                >
                    <div
                        className={summary.status === 'exhausted' ? 'h-full bg-amber-500' : 'h-full bg-emerald-500'}
                        style={{ width: `${percent}%` }}
                    />
                </div>
            ) : null}
            {summary.status === 'exhausted' ? (
                <p className="text-sm text-amber-800">{STATUS_MESSAGES.exhausted.description}</p>
            ) : sessions ? (
                <p className="text-sm text-slate-500">
                    Quedan {formatNumber(sessions.available_included)} conversaciones incluidas.
                </p>
            ) : null}
            {variant === 'full' && summary.period ? (
                <dl className="grid gap-2 text-sm sm:grid-cols-2">
                    <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-400">Período</dt>
                        <dd className="text-slate-700">
                            {formatDateFromTimestampAR(summary.period.start)} al {formatDateFromTimestampAR(summary.period.end)}
                        </dd>
                    </div>
                    {summary.scheduled_change ? (
                        <div>
                            <dt className="text-xs uppercase tracking-wide text-slate-400">Próximo cupo</dt>
                            <dd className="text-slate-700">
                                {formatNumber(summary.scheduled_change.included_sessions)} desde{' '}
                                {formatDateFromTimestampAR(summary.scheduled_change.effective_at)}
                            </dd>
                        </div>
                    ) : null}
                </dl>
            ) : null}
            {variant === 'full' ? (
                <p className="text-xs text-slate-400">
                    Cada conversación con un cliente cuenta como una sesión de hasta 24 horas.
                    {summary.overage && !summary.overage.enabled
                        ? ' Sin excedentes: al agotarse el cupo, el agente no inicia conversaciones nuevas.'
                        : ''}
                </p>
            ) : null}
        </section>
    );
}
