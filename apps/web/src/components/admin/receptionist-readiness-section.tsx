'use client';

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { SectionCard } from '@/components/admin/section-card';
import { StatusBadge } from '@/components/admin/status-badge';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal';
import { Switch } from '@/components/ui/switch';
import { useAdminAIUsage, useAdminWhatsAppConnections } from '@/features/reception/hooks';
import type { ReceptionistConfigAdapter } from '@/features/reception/receptionist-config-api';
import { ATTENTION_LABELS, attentionStateOf, errorCode } from '@/features/reception/receptionist-config-form';
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
 *
 * PROD-09C3: incluye el interruptor «Atención automática» (único control
 * operativo, `automatic_attention_enabled`); el checklist informa, nunca
 * autoriza.
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
    businessName: string;
    owner: AdminMember | null;
    config: QueryLike<ReceptionistConfigResponse>;
    /** Adaptador `platform_admin` del bloque: mismo PATCH y misma query key que el formulario. */
    adapter: ReceptionistConfigAdapter;
};

type Notice = { tone: 'success' | 'error'; text: string; reload?: boolean } | null;

function attentionError(error: unknown): Notice {
    const code = errorCode(error);
    if (code === 'version_conflict') {
        return {
            tone: 'error',
            text: 'La configuración cambió desde que la cargaste. Recargá el estado antes de volver a intentarlo; no se cambió nada.',
            reload: true,
        };
    }
    if (error instanceof ApiError && error.status === 403) {
        return { tone: 'error', text: 'Tu rol de Platform Admin no puede cambiar la atención automática.' };
    }
    if (code === 'validation_error') {
        return { tone: 'error', text: 'Mi Rubro no aceptó el cambio: la configuración tiene que estar «lista» para habilitarla.' };
    }
    const detail = (error instanceof ApiError ? (error.payload as { detail?: unknown } | undefined)?.detail : null);
    return {
        tone: 'error',
        text: typeof detail === 'string' && detail ? detail : 'No pudimos cambiar la atención automática. Intentá nuevamente.',
    };
}

/**
 * PROD-09C3 — Interruptor «Atención automática». Fuente de verdad:
 * `automatic_attention_enabled` de la configuración (nunca el checklist).
 * Usa el PATCH admin existente con `expected_version` y el flag solamente;
 * el interruptor refleja el backend (sin estado optimista) y la respuesta
 * actualiza la misma query que lee el formulario.
 */
function AttentionControl({ businessName, config, adapter, openConditions }: {
    businessName: string;
    config: QueryLike<ReceptionistConfigResponse>;
    adapter: ReceptionistConfigAdapter;
    openConditions: number;
}) {
    const queryClient = useQueryClient();
    const [confirm, setConfirm] = useState<boolean | null>(null);
    const [pending, setPending] = useState(false);
    const [notice, setNotice] = useState<Notice>(null);

    const current = config.data?.config ?? null;
    const state = attentionStateOf(current);
    const badge = ATTENTION_LABELS[state];
    const ready = current?.status === 'ready';
    const enabled = state === 'enabled';
    // Pausar nunca depende del estado comercial; habilitar exige «lista».
    const disabled = !current || state === 'unknown' || pending || (!enabled && !ready);

    const apply = async () => {
        if (!current || confirm === null) return;
        const target = confirm;
        setPending(true);
        setNotice(null);
        try {
            const response = await adapter.patch({
                expected_version: current.version,
                automatic_attention_enabled: target,
            });
            queryClient.setQueryData(adapter.key, response);
            setNotice({
                tone: 'success',
                text: target ? 'Atención automática habilitada.' : 'Atención automática pausada.',
            });
        } catch (error) {
            setNotice(attentionError(error));
        } finally {
            setPending(false);
            setConfirm(null);
        }
    };

    const reload = async () => {
        setNotice(null);
        // El formulario protege sus cambios sin guardar si el contenido cambió.
        await queryClient.refetchQueries({ queryKey: adapter.key });
    };

    return (
        <section aria-labelledby="attention-title" className="space-y-2 rounded-lg border border-slate-200 p-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                    <h4 id="attention-title" className="text-sm font-semibold text-slate-800">Atención automática</h4>
                    <StatusBadge label={badge.label} colorClass={badge.className} />
                </div>
                <label className="flex items-center gap-2 text-sm text-slate-700">
                    <Switch
                        aria-label="Atención automática"
                        checked={enabled}
                        disabled={disabled}
                        onCheckedChange={(value) => setConfirm(value)}
                    />
                    {pending ? 'Guardando…' : enabled ? 'Habilitada' : 'Pausada'}
                </label>
            </div>
            <p className="text-xs text-slate-500">
                Solo se activa desde acá: nunca al completar la configuración, contratar el servicio ni vincular
                WhatsApp. Volver la configuración a borrador también la pausa, y marcarla otra vez como lista no la
                reactiva. Habilitada no significa que el agente esté conectado ni respondiendo.
            </p>
            {state === 'unknown' && current ? (
                <p className="text-xs text-slate-600">No pudimos verificar el estado de la atención automática.</p>
            ) : null}
            {current && !ready && !enabled ? (
                <p className="text-xs text-amber-800">Para habilitarla, la configuración tiene que estar «lista».</p>
            ) : null}
            {current && ready && !enabled && openConditions > 0 ? (
                <p className="text-xs text-amber-800">
                    Hay {openConditions} condición(es) comercial(es) o técnica(s) sin cumplir o sin verificar. Mi Rubro
                    sigue controlando el consumo en cada interacción.
                </p>
            ) : null}
            {notice ? (
                <div className={notice.tone === 'success' ? 'text-xs text-emerald-700' : 'text-xs text-rose-700'} role="status">
                    <p>{notice.text}</p>
                    {notice.reload ? (
                        <Button type="button" variant="outline" size="sm" className="mt-2" onClick={reload}>
                            Recargar estado
                        </Button>
                    ) : null}
                </div>
            ) : null}

            <Modal
                open={confirm !== null}
                title={confirm ? '¿Habilitar la atención automática?' : '¿Pausar la atención automática?'}
                eyebrow={null}
                onClose={() => (pending ? undefined : setConfirm(null))}
                footer={
                    <div className="flex justify-end gap-2">
                        <Button type="button" variant="outline" disabled={pending} onClick={() => setConfirm(null)}>
                            Cancelar
                        </Button>
                        <Button type="button" disabled={pending} onClick={apply}>
                            {confirm ? 'Habilitar' : 'Pausar'}
                        </Button>
                    </div>
                }
            >
                <p className="text-sm text-slate-600">
                    Comercio: <span className="font-medium text-slate-800">{businessName}</span>
                </p>
                <p className="mt-2 text-sm text-slate-600">
                    {confirm
                        ? 'El agente podrá responder solo las consultas nuevas de este comercio, mientras Mi Rubro autorice el consumo. No garantiza que el agente esté conectado: lo que no se verifica desde Mi Rubro sigue pendiente.'
                        : 'Las consultas nuevas de este comercio pasan al equipo y no se responden automáticamente. Al volver a habilitarla, los mensajes del período pausado no se responden.'}
                </p>
            </Modal>
        </section>
    );
}

const GROUPS: Array<{ title: string; keys: string[] }> = [
    { title: 'Cuenta y configuración', keys: ['owner', 'config'] },
    { title: 'Estado comercial', keys: ['access', 'policy'] },
    { title: 'Conexiones (estado local)', keys: ['channel', 'auth', 'instance'] },
];

export function ReceptionistReadinessSection({ businessId, businessName, owner, config, adapter }: Props) {
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
                        ? 'Condiciones locales cumplidas. Lo que no se verifica desde Mi Rubro sigue pendiente de comprobar.'
                        : `${open} de ${rows.length} condiciones sin cumplir o sin verificar.`}
                </p>
                {GROUPS.map((group) => (
                    <div key={group.title}>
                        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">{group.title}</h4>
                        <ul className="divide-y divide-slate-100">
                            {rows.filter((row) => group.keys.includes(row.key)).map((row) => (
                                <li key={row.key} className="flex flex-wrap items-start justify-between gap-2 py-2">
                                    <div className="min-w-0">
                                        <p className="text-sm font-medium text-slate-800">{row.label}</p>
                                        <p className="text-xs text-slate-500">{row.detail}</p>
                                    </div>
                                    <StatusBadge label={STATE_BADGE[row.state].label} colorClass={STATE_BADGE[row.state].color} />
                                </li>
                            ))}
                        </ul>
                    </div>
                ))}
                {channel.note ? <p className="text-xs text-slate-500">{channel.note}</p> : null}
                <AttentionControl businessName={businessName} config={config} adapter={adapter} openConditions={open} />
                <div className="rounded-lg bg-slate-50 p-3">
                    <p className="text-xs font-medium text-slate-600">No verificable desde Mi Rubro</p>
                    <ul className="mt-1 list-disc pl-4 text-xs text-slate-500">
                        {NOT_VERIFIABLE.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                </div>
            </div>
        </SectionCard>
    );
}
