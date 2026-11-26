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

const STATUS_MESSAGES: Record<Exclude<AIUsageSummary['status'], 'available'>, { title: string; description: string }> = {
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
};

function tierLabel(summary: AIUsageSummary): string | null {
    const tier = summary.source?.usage_tier;
    if (!tier) return null;
    return TIER_LABELS[tier] ?? null;
}

function errorMessage(error: unknown): { title: string; description: string } {
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

    if (query.isLoading) {
        return (
            <section aria-busy="true" className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <p className="text-sm text-slate-500">Cargando consumo…</p>
            </section>
        );
    }

    if (query.isError || !query.data) {
        const message = errorMessage(query.error);
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
        const message = STATUS_MESSAGES[summary.status] ?? STATUS_MESSAGES.unavailable;
        return (
            <section role="status" className="rounded-2xl border border-amber-200 bg-amber-50 p-4 shadow-sm">
                <h2 className="text-sm font-semibold text-amber-900">{message.title}</h2>
                <p className="text-sm text-amber-800">{message.description}</p>
                {tier ? <p className="mt-1 text-xs text-amber-700">Plan: {tier}</p> : null}
            </section>
        );
    }

    const sessions = summary.sessions;
    const used = sessions?.used ?? 0;
    const included = sessions?.included ?? 0;
    const percent = included > 0 ? Math.min(100, Math.round((used / included) * 100)) : 0;

    return (
        <section aria-labelledby="ai-usage-title" className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <header className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 id="ai-usage-title" className="text-sm font-semibold text-slate-800">Conversaciones del período</h2>
                {tier ? <span className="text-xs text-slate-500">{tier}</span> : null}
            </header>
            <p className="text-2xl font-semibold text-slate-900">
                {formatNumber(used)} <span className="text-base font-normal text-slate-500">de {formatNumber(included)}</span>
            </p>
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
            {summary.status === 'exhausted' ? (
                <p className="text-sm text-amber-800">{STATUS_MESSAGES.exhausted.description}</p>
            ) : (
                <p className="text-sm text-slate-500">
                    Quedan {formatNumber(sessions?.available_included ?? 0)} conversaciones incluidas.
                </p>
            )}
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
