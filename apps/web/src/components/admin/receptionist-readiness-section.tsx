'use client';

import { SectionCard } from '@/components/admin/section-card';
import { StatusBadge } from '@/components/admin/status-badge';
import { useAdminAIUsage, useAdminWhatsAppConnections } from '@/features/reception/hooks';
import type {
    AdminAIUsageOverview,
    AdminWhatsAppChannel,
    AdminWhatsAppConnections,
    ReceptionistConfigResponse,
} from '@/features/reception/types';
import type { AdminMember } from '@/lib/admin/types';
import { ApiError } from '@/lib/api/client';

/**
 * PROD-09B — «Preparación del agente»: resumen DERIVADO de lo que el bloque
 * Recepcionista ya consulta (configuración, consumo, conexiones) y del owner
 * del detalle. Mismas query keys y mismo `Providers`: no agrega requests.
 * No recalcula reglas: usa `diagnosis.code`, `summary.status`,
 * `config.status` y `local_status` tal como llegan.
 */

export type ReadinessState = 'met' | 'partial' | 'pending' | 'blocked' | 'unknown';

const STATE_BADGE: Record<ReadinessState, { label: string; color: string }> = {
    met: { label: 'Cumplida', color: 'bg-emerald-100 text-emerald-700' },
    partial: { label: 'Verificación parcial', color: 'bg-sky-100 text-sky-700' },
    pending: { label: 'Pendiente', color: 'bg-amber-100 text-amber-800' },
    blocked: { label: 'Bloqueada', color: 'bg-red-100 text-red-700' },
    unknown: { label: 'Desconocida', color: 'bg-slate-100 text-slate-600' },
};

type Row = { key: string; label: string; state: ReadinessState; detail: string };
type QueryLike<T> = { isLoading: boolean; isError: boolean; data?: T; error: unknown };

function notLoaded(query: QueryLike<unknown>): string | null {
    if (query.isLoading) return 'Cargando…';
    if (query.isError || query.data === undefined) {
        return query.error instanceof ApiError && query.error.status === 403
            ? 'Sin acceso para verificarla.'
            : 'No se pudo cargar el dato.';
    }
    return null;
}

function ownerRow(owner: AdminMember | null): Row {
    const base = { key: 'owner', label: 'Cuenta owner y membership' };
    if (!owner) return { ...base, state: 'pending', detail: 'El comercio no tiene un owner con membership activa.' };
    return {
        ...base,
        state: 'partial',
        detail: `${owner.email} con membership activa. No se verifica si vinculó Google ni si ya ingresó.`,
    };
}

// Diagnóstico PROD-02E3B: el primer motivo que bloquea. Los de ciclo de vida
// dicen si hay acceso comercial; los posteriores implican que el acceso pasó.
const ACCESS_BLOCKED = new Set([
    'no_ai_subscription', 'subscription_canceled', 'subscription_suspended', 'past_due_grace_expired',
    'subscription_not_active', 'benefit_expired', 'canceled_at_period_end', 'business_not_active',
]);
const ACCESS_PENDING = new Set(['benefit_not_started']);
const ACCESS_UNDETERMINED = new Set(['ambiguous_ai_source', 'resolution_error']);
const ACCESS_PASSED = new Set([
    'ok', 'quota_exhausted', 'invalid_tier', 'custom_policy_missing', 'custom_policy_revoked',
    'custom_policy_not_started', 'custom_policy_expired', 'usage_policy_undefined',
    'reception_kill_switch_disabled', 'metering_disabled', 'usage_unavailable',
]);

function accessRow(query: QueryLike<AdminAIUsageOverview>): Row {
    const base = { key: 'access', label: 'Acceso comercial vigente' };
    const missing = notLoaded(query);
    if (missing) return { ...base, state: 'unknown', detail: missing };
    const { code } = query.data!.diagnosis;
    const sub = query.data!.source_subscription;
    const subText = sub ? `Suscripción ${sub.status}${sub.complimentary ? ' (bonificada)' : ''}.` : 'Sin suscripción de IA.';
    if (ACCESS_PASSED.has(code)) return { ...base, state: 'met', detail: subText };
    if (ACCESS_BLOCKED.has(code)) return { ...base, state: 'blocked', detail: `${subText} Diagnóstico: ${code}.` };
    if (ACCESS_PENDING.has(code)) return { ...base, state: 'pending', detail: `${subText} La bonificación todavía no empezó.` };
    if (ACCESS_UNDETERMINED.has(code)) return { ...base, state: 'unknown', detail: `No se pudo determinar (${code}).` };
    return { ...base, state: 'unknown', detail: `Diagnóstico no reconocido (${code}).` };
}

function policyRow(query: QueryLike<AdminAIUsageOverview>): Row {
    const base = { key: 'policy', label: 'Política IA y cupo disponible' };
    const missing = notLoaded(query);
    if (missing) return { ...base, state: 'unknown', detail: missing };
    const summary = query.data!.summary;
    if (!summary) return { ...base, state: 'unknown', detail: 'El consumo no pudo evaluarse.' };
    const sessions = summary.sessions;
    switch (summary.status) {
        case 'available':
            return {
                ...base, state: 'met',
                detail: sessions ? `Quedan ${sessions.available_included} de ${sessions.included} sesiones.` : 'Cupo disponible.',
            };
        case 'exhausted':
            return { ...base, state: 'blocked', detail: 'Cupo del período agotado.' };
        case 'policy_not_configured':
            return { ...base, state: 'pending', detail: 'Sin cupo vigente configurado.' };
        case 'suspended':
        case 'not_contracted':
        case 'ambiguous_source':
            return { ...base, state: 'blocked', detail: `Consumo no autorizado (${summary.status}).` };
        case 'unavailable':
            return { ...base, state: 'unknown', detail: `Medición no disponible (${summary.reason ?? 'sin motivo'}).` };
        default:
            return { ...base, state: 'unknown', detail: `Estado no reconocido (${String(summary.status)}).` };
    }
}

function configRow(query: QueryLike<ReceptionistConfigResponse>): Row {
    const base = { key: 'config', label: 'Configuración «lista»' };
    const missing = notLoaded(query);
    if (missing) return { ...base, state: 'unknown', detail: missing };
    const config = query.data!.config;
    if (!config) return { ...base, state: 'pending', detail: 'Todavía no hay configuración del agente.' };
    if (config.status === 'ready') return { ...base, state: 'met', detail: 'Configuración completa y marcada como lista.' };
    const count = config.missing_for_ready.length;
    return {
        ...base, state: 'pending',
        detail: count > 0 ? `En borrador; faltan ${count} campos obligatorios.` : 'En borrador.',
    };
}

/**
 * Canal sobre el que se evalúan canal, autorización e instancia (siempre el
 * MISMO): primero uno con credencial vigente, después uno con credencial
 * vigente pero instancia deshabilitada, después el primer activo, después el
 * primero. Nunca combina estados de canales distintos.
 */
export function pickChannel(channels: AdminWhatsAppChannel[]): AdminWhatsAppChannel | null {
    return channels.find((c) => c.local_status === 'credential_ready')
        ?? channels.find((c) => c.local_status === 'agent_instance_disabled')
        ?? channels.find((c) => c.is_active)
        ?? channels[0]
        ?? null;
}

const AUTH_FROM_LOCAL_STATUS: Record<string, { state: ReadinessState; detail: string }> = {
    credential_ready: { state: 'partial', detail: 'Vigente en Mi Rubro; no verificada con Meta.' },
    agent_instance_disabled: { state: 'partial', detail: 'Vigente en Mi Rubro; no verificada con Meta.' },
    channel_not_active: { state: 'unknown', detail: 'No evaluada: el canal está desactivado.' },
    whatsapp_authorization_missing: { state: 'pending', detail: 'El canal no tiene autorización.' },
    whatsapp_waba_missing: { state: 'pending', detail: 'Falta la WABA del canal.' },
    whatsapp_authorization_owner_mismatch: { state: 'blocked', detail: 'Autorización inconsistente.' },
    whatsapp_authorization_revoked: { state: 'blocked', detail: 'Autorización revocada.' },
    whatsapp_authorization_invalid: { state: 'blocked', detail: 'Autorización inválida.' },
    whatsapp_authorization_expired: { state: 'blocked', detail: 'Autorización vencida.' },
};

function channelRows(query: QueryLike<AdminWhatsAppConnections>): { rows: Row[]; note: string | null } {
    const labels = {
        channel: 'Canal WhatsApp activo',
        auth: 'Autorización local vigente',
        instance: 'Instancia asignada y habilitada',
    };
    const missing = notLoaded(query);
    if (missing) {
        return {
            rows: (['channel', 'auth', 'instance'] as const).map((key) => ({ key, label: labels[key], state: 'unknown', detail: missing })),
            note: null,
        };
    }
    const channels = query.data!.channels;
    const channel = pickChannel(channels);
    if (!channel) {
        return {
            rows: [
                { key: 'channel', label: labels.channel, state: 'pending', detail: 'No hay canales registrados.' },
                { key: 'auth', label: labels.auth, state: 'unknown', detail: 'No evaluada: no hay canal.' },
                { key: 'instance', label: labels.instance, state: 'unknown', detail: 'No evaluada: no hay canal.' },
            ],
            note: null,
        };
    }
    const auth = AUTH_FROM_LOCAL_STATUS[channel.local_status]
        ?? { state: 'unknown' as const, detail: `Estado no reconocido (${channel.local_status}).` };
    const instance = channel.agent_instance;
    return {
        rows: [
            {
                key: 'channel', label: labels.channel,
                state: channel.is_active ? 'met' : 'blocked',
                detail: channel.is_active ? 'Canal activo.' : 'El canal está desactivado.',
            },
            { key: 'auth', label: labels.auth, ...auth },
            {
                key: 'instance', label: labels.instance,
                state: instance.is_enabled ? 'met' : 'blocked',
                detail: instance.is_enabled ? `${instance.name}, habilitada.` : `${instance.name}, deshabilitada.`,
            },
        ],
        note: `Canal evaluado: Phone Number ID ${channel.phone_number_id}`
            + (channels.length > 1 ? ` (${channels.length} canales registrados; ver «Conexiones WhatsApp»).` : '.'),
    };
}

const NOT_VERIFIABLE = [
    'Conectividad real con Meta (webhook, permisos del token, número registrado).',
    'Que el proceso del agente esté online.',
    'Flags del entorno (Mi Rubro y agente).',
    'Una conversación real de prueba.',
];

type Props = {
    businessId: number;
    owner: AdminMember | null;
    config: QueryLike<ReceptionistConfigResponse>;
};

export function ReceptionistReadinessSection({ businessId, owner, config }: Props) {
    const usage = useAdminAIUsage(businessId);
    const connections = useAdminWhatsAppConnections(businessId);
    const channel = channelRows(connections);
    const rows: Row[] = [ownerRow(owner), accessRow(usage), policyRow(usage), configRow(config), ...channel.rows];
    const open = rows.filter((row) => row.state !== 'met' && row.state !== 'partial').length;

    return (
        <SectionCard
            title="Preparación del agente"
            description="Condiciones registradas en Mi Rubro. No indica que el agente esté conectado ni operativo."
        >
            <div className="space-y-4">
                <p role="status" className="text-sm text-slate-700">
                    {open === 0
                        ? 'Condiciones locales cumplidas. Puede haber atención automática: lo que no se verifica desde Mi Rubro sigue pendiente de comprobar.'
                        : `${open} de ${rows.length} condiciones sin cumplir o sin verificar.`}
                </p>
                <ul className="divide-y divide-slate-100">
                    {rows.map((row) => (
                        <li key={row.key} className="flex flex-wrap items-start justify-between gap-2 py-2">
                            <div className="min-w-0">
                                <p className="text-sm font-medium text-slate-800">{row.label}</p>
                                <p className="text-xs text-slate-500">{row.detail}</p>
                            </div>
                            <StatusBadge label={STATE_BADGE[row.state].label} colorClass={STATE_BADGE[row.state].color} />
                        </li>
                    ))}
                </ul>
                {channel.note ? <p className="text-xs text-slate-500">{channel.note}</p> : null}
                <div className="rounded-lg bg-slate-50 p-3">
                    <p className="text-xs font-medium text-slate-600">No verificable desde Mi Rubro</p>
                    <ul className="mt-1 list-disc pl-4 text-xs text-slate-500">
                        {NOT_VERIFIABLE.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                </div>
                <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                    La atención automática empieza sola cuando se cumplen las condiciones técnicas y comerciales: no hay
                    un interruptor independiente. Para cortarla en este comercio, volvé la configuración a «Borrador».
                </p>
            </div>
        </SectionCard>
    );
}
