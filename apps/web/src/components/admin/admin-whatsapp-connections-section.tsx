'use client';

import { RefreshCw } from 'lucide-react';

import { EmptyState } from '@/components/admin/empty-state';
import { ErrorState } from '@/components/admin/error-state';
import { LoadingState } from '@/components/admin/loading-state';
import { SectionCard } from '@/components/admin/section-card';
import { StatusBadge } from '@/components/admin/status-badge';
import { Button } from '@/components/ui/button';
import { useAdminWhatsAppConnections } from '@/features/reception/hooks';
import type { AdminWhatsAppChannel, AdminWhatsAppConnections } from '@/features/reception/types';
import { ApiError } from '@/lib/api/client';
import { formatDateTimeAR } from '@/lib/dates';

const OK = 'bg-emerald-100 text-emerald-700';
const WARN = 'bg-amber-100 text-amber-800';
const BAD = 'bg-red-100 text-red-700';
const NEUTRAL = 'bg-slate-100 text-slate-600';

/**
 * Textos de `local_status` (PROD-08E1). El backend decide el estado: el
 * frontend nunca recalcula reglas de autorización. Un código no listado se
 * muestra como no reconocido, nunca como válido.
 */
const LOCAL_STATUS: Record<string, { label: string; color: string }> = {
    credential_ready: { label: 'Credencial vigente (estado local)', color: OK },
    channel_not_active: { label: 'Canal desactivado', color: NEUTRAL },
    whatsapp_authorization_missing: { label: 'Sin autorización', color: WARN },
    whatsapp_authorization_owner_mismatch: { label: 'Autorización inconsistente', color: BAD },
    whatsapp_authorization_revoked: { label: 'Autorización revocada', color: BAD },
    whatsapp_authorization_invalid: { label: 'Autorización inválida', color: BAD },
    whatsapp_authorization_expired: { label: 'Autorización vencida', color: WARN },
    whatsapp_waba_missing: { label: 'WABA no informada', color: WARN },
    agent_instance_disabled: { label: 'Instancia deshabilitada', color: WARN },
};

const AUTH_KIND: Record<string, string> = { business: 'Del comercio', platform: 'De plataforma' };
const AUTH_STATUS: Record<string, string> = { active: 'activa', revoked: 'revocada', invalid: 'inválida' };

function localStatus(code: string) {
    return LOCAL_STATUS[code] ?? { label: `Estado no reconocido (${code})`, color: BAD };
}

function date(value: string | null | undefined): string {
    return value ? formatDateTimeAR(value) : 'Sin dato';
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div className="min-w-0">
            <dt className="text-xs uppercase tracking-wide text-slate-400">{label}</dt>
            <dd className="break-words text-sm text-slate-700">{children}</dd>
        </div>
    );
}

function ChannelItem({ channel }: { channel: AdminWhatsAppChannel }) {
    const status = localStatus(channel.local_status);
    const auth = channel.authorization;
    const instance = channel.agent_instance;

    return (
        <li className="space-y-3 rounded-lg border border-slate-200 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm text-slate-500">
                    Phone Number ID{' '}
                    <span className="font-mono font-medium text-slate-900">{channel.phone_number_id}</span>
                </p>
                <StatusBadge label={status.label} colorClass={status.color} />
            </div>
            <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {channel.waba_id ? (
                    <Field label="WABA ID"><span className="font-mono">{channel.waba_id}</span></Field>
                ) : null}
                <Field label="Canal">
                    {channel.is_active ? 'Activo' : `Desactivado · ${date(channel.deactivated_at)}`}
                </Field>
                <Field label="Instancia del agente">
                    {instance.name} · {instance.is_enabled ? 'habilitada' : `deshabilitada · ${date(instance.disabled_at)}`}
                </Field>
                <Field label="Autorización">
                    {auth
                        ? `${AUTH_KIND[auth.kind] ?? 'Tipo no reconocido'} · ${AUTH_STATUS[auth.status] ?? 'estado no reconocido'}`
                        : 'Sin autorización'}
                </Field>
                {auth ? (
                    <Field label="Vencimiento">
                        {auth.expires_at ? `${date(auth.expires_at)}${auth.expired ? ' · vencida' : ''}` : 'Sin vencimiento informado'}
                    </Field>
                ) : null}
                {auth?.revoked_at ? <Field label="Revocada">{date(auth.revoked_at)}</Field> : null}
                <Field label="Alta del canal">{date(channel.created_at)}</Field>
            </dl>
        </li>
    );
}

function Body({ data }: { data: AdminWhatsAppConnections }) {
    return (
        <div className="space-y-4">
            <p className="text-xs text-slate-500">
                Estado local registrado en Mi Rubro, evaluado el {date(data.evaluated_at)}.{' '}
                {data.external_verification.performed
                    ? null
                    : 'No se realizó verificación externa con Meta: no indica WhatsApp conectado, agente online ni envío disponible.'}
            </p>
            {data.channels.length === 0 ? (
                <EmptyState
                    title="Sin canales WhatsApp registrados"
                    description="Este cliente no tiene canales asociados a una instancia del agente."
                />
            ) : (
                <ul className="space-y-3">
                    {data.channels.map((channel) => <ChannelItem key={channel.id} channel={channel} />)}
                </ul>
            )}
        </div>
    );
}

function errorMessage(error: unknown): string {
    if (error instanceof ApiError && error.status === 403) return 'Tu rol de Platform Admin no puede ver las conexiones WhatsApp.';
    return 'No pudimos cargar las conexiones WhatsApp. Intentá nuevamente en unos minutos.';
}

/**
 * PROD-08E2 — Canales y autorizaciones WhatsApp del cliente: estado local
 * de PROD-08E1, solo lectura. Sin polling; «Actualizar» vuelve a consultar.
 */
export function AdminWhatsAppConnectionsSection({ businessId }: { businessId: number }) {
    const query = useAdminWhatsAppConnections(businessId);

    let body: React.ReactNode;
    if (query.isLoading) body = <LoadingState message="Cargando conexiones…" className="py-8" />;
    else if (query.isError || !query.data) {
        body = <ErrorState title="Conexiones no disponibles" message={errorMessage(query.error)} retry={() => void query.refetch()} />;
    } else body = <Body data={query.data} />;

    return (
        <SectionCard
            title="Conexiones WhatsApp"
            description="Canales y autorizaciones registrados en Mi Rubro. No se administran desde acá."
            actions={(
                <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => void query.refetch()}
                    disabled={query.isFetching}
                >
                    <RefreshCw className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                    {query.isFetching && !query.isLoading ? 'Actualizando…' : 'Actualizar'}
                </Button>
            )}
        >
            {body}
        </SectionCard>
    );
}
