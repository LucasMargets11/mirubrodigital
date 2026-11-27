'use client';

import { useState } from 'react';

import { SectionCard } from '@/components/admin/section-card';
import { StatCard } from '@/components/admin/stat-card';
import { DateRangePicker, type DateRange } from '@/components/ui/date-range-picker';
import type { MetricsRange } from '@/features/reception/api';
import { useAdminOperationalMetrics } from '@/features/reception/hooks';
import type { OperationalMetrics } from '@/features/reception/types';
import { ApiError } from '@/lib/api/client';
import { formatDateAR, localDateToString, parseDateOnly } from '@/lib/dates';
import { formatNumber } from '@/lib/format';

/** Mismo límite que el backend (`MAX_RANGE_DAYS`, PROD-02E4C). */
const MAX_RANGE_DAYS = 92;
const UNKNOWN = 'Sin datos';

const NO_COST_REASONS: Record<string, string> = {
    tokens_unknown: 'sin tokens informados',
    cached_tokens_unknown: 'sin tokens cacheados informados',
    no_rate: 'sin tarifa verificada',
    ambiguous_rate: 'tarifa ambigua',
};

/** `null` = el backend no tiene el dato: nunca se muestra como 0. */
function count(value: number | null | undefined): string {
    return value === null || value === undefined ? UNKNOWN : formatNumber(value);
}

function usd(value: string): string {
    return formatNumber(value, { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

function rangeError(range: MetricsRange): string | null {
    if (!range.date_from || !range.date_to) return null;
    const from = parseDateOnly(range.date_from).getTime();
    const to = parseDateOnly(range.date_to).getTime();
    if (from > to) return 'La fecha «Desde» debe ser anterior o igual a «Hasta».';
    if (Math.round((to - from) / 86_400_000) + 1 > MAX_RANGE_DAYS) {
        return `El rango no puede superar ${MAX_RANGE_DAYS} días.`;
    }
    return null;
}

function errorText(error: unknown): string {
    if (error instanceof ApiError && error.status === 403) return 'Tu rol de Platform Admin no puede ver las métricas operativas.';
    if (error instanceof ApiError && error.status === 400) return 'El rango de fechas no es válido.';
    return 'No pudimos cargar las métricas. Intentá nuevamente en unos minutos.';
}

function Rows({ rows }: { rows: Array<[string, string]> }) {
    return (
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
            {rows.map(([label, value]) => (
                <div key={label} className="flex justify-between gap-4 border-b border-slate-100 py-1">
                    <dt className="text-slate-500">{label}</dt>
                    <dd className="font-medium text-slate-800">{value}</dd>
                </div>
            ))}
        </dl>
    );
}

function Block({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
    return (
        <section className="space-y-3">
            <h4 className="text-sm font-semibold text-slate-800">{title}</h4>
            {children}
            {note ? <p className="text-xs text-slate-400">{note}</p> : null}
        </section>
    );
}

function WhatsAppBlock({ w }: { w: OperationalMetrics['whatsapp'] }) {
    return (
        <Block
            title="WhatsApp"
            note="Mensajes registrados por el agente en episodios de leads; el estado es el último sincronizado. No distingue respuestas de IA y automáticas. No son conversaciones facturables de Meta."
        >
            {!w.available ? (
                <p role="status" className="text-sm text-amber-800">
                    Sin datos de WhatsApp: {w.coverage.has_agent_channel
                        ? 'no se observó sincronización del agente.'
                        : 'el cliente no tiene canal del agente.'}
                </p>
            ) : null}
            <div className="grid gap-4 sm:grid-cols-3">
                <StatCard title="Recibidos" value={count(w.totals.inbound)} />
                <StatCard
                    title="Enviados"
                    value={count(w.totals.outbound)}
                    description={`Bot ${count(w.by_sender.bot)} · Recepción ${count(w.by_sender.staff)}`}
                />
                <StatCard title="Conversaciones con actividad" value={count(w.conversations.with_activity)} />
            </div>
            <Rows rows={[
                ['Entregados', count(w.outbound_status.delivered)],
                ['Leídos', count(w.outbound_status.read)],
                ['Enviados sin confirmar', count(w.outbound_status.sent)],
                ['Fallidos', count(w.outbound_status.failed)],
                ['Sin estado informado', count(w.outbound_status.unknown)],
            ]} />
        </Block>
    );
}

function HandoffBlock({ w }: { w: OperationalMetrics['whatsapp'] }) {
    return (
        <Block title="Derivaciones y atención humana">
            <Rows rows={[
                ['Derivaciones solicitadas', count(w.handoffs.requested)],
                ['Bot pausado para recepción', count(w.handoffs.bot_paused_for_reception)],
                ['Tomas de conversación', count(w.handoffs.takeovers_applied)],
                ['Devoluciones al bot', count(w.handoffs.releases_applied)],
                ['Mensajes de recepción desde Mi Rubro', formatNumber(w.staff_messages.requested)],
                ['… con error de envío al agente', formatNumber(w.staff_messages.failed)],
            ]} />
        </Block>
    );
}

function AIBlock({ a }: { a: OperationalMetrics['openai_activity'] }) {
    const { input, output } = a.tokens;
    const tokensKnown = input.total !== null || output.total !== null;
    return (
        <Block title="Ejecuciones de IA (OpenAI)" note="Intentos reales contra el proveedor informados por el agente; requieren la telemetría del agente activa.">
            <div className="grid gap-4 sm:grid-cols-3">
                <StatCard
                    title="Ejecuciones"
                    value={formatNumber(a.executions)}
                    description={`${formatNumber(a.by_status.succeeded ?? 0)} ok · ${formatNumber(a.by_status.failed ?? 0)} fallidas · ${formatNumber(a.by_status.unknown ?? 0)} desconocidas`}
                />
                <StatCard
                    title="Tokens reportados"
                    value={tokensKnown ? `${count(input.total)} / ${count(output.total)}` : UNKNOWN}
                    description={`Entrada / salida · sin informar en ${formatNumber(input.unknown)} ejecuciones`}
                />
                <StatCard
                    title="Latencia promedio"
                    value={a.latency_ms.average === null ? UNKNOWN : `${formatNumber(a.latency_ms.average)} ms`}
                    description={a.latency_ms.p95 === null
                        ? `p95 con al menos ${a.latency_ms.p95_min_samples} muestras`
                        : `p95 ${formatNumber(a.latency_ms.p95)} ms`}
                />
            </div>
        </Block>
    );
}

function CostBlock({ c, executions }: { c: OperationalMetrics['openai_costs']; executions: number }) {
    const noneCosted = c.costed_executions === 0 && c.uncosted_executions > 0;
    const reasons = Object.entries(c.uncosted_reasons)
        .filter(([, n]) => n > 0)
        .map(([reason, n]) => `${formatNumber(n)} ${NO_COST_REASONS[reason] ?? reason}`);
    let description: string;
    if (executions === 0) description = 'Sin ejecuciones en el período.';
    else if (noneCosted) description = 'Ninguna ejecución pudo estimarse.';
    else if (!c.complete) description = `Parcial: ${formatNumber(c.uncosted_executions)} ejecuciones sin estimar.`;
    else description = `Completo: ${formatNumber(c.costed_executions)} ejecuciones estimadas.`;

    return (
        <Block
            title="Costos operativos estimados"
            note="Estimación en USD con tarifas verificadas de OpenAI. No es facturación ni consumo comercial del cliente."
        >
            <div className="grid gap-4 sm:grid-cols-2">
                <StatCard title="OpenAI (estimado)" value={noneCosted ? UNKNOWN : usd(c.estimated_total)} description={description} />
                <StatCard title="Meta / WhatsApp" value={UNKNOWN} description="Mi Rubro no recibe costos de Meta." />
            </div>
            {reasons.length > 0 ? <p className="text-xs text-amber-800">Sin estimar: {reasons.join(' · ')}.</p> : null}
        </Block>
    );
}

function CoverageBlock({ m }: { m: OperationalMetrics }) {
    const w = m.whatsapp.coverage;
    return (
        <Block title="Cobertura">
            <Rows rows={[
                ['Canal del agente', w.has_agent_channel ? 'Sí' : 'No'],
                ['Sincronización observada', w.sync_observed ? 'Sí' : 'No'],
                ['Leads en el tope de mensajes sincronizados', formatNumber(w.leads_at_message_cap)],
                ['Ejecuciones sin tokens informados', formatNumber(m.openai_activity.tokens.input.unknown)],
            ]} />
        </Block>
    );
}

/**
 * PROD-08D — Métricas operativas del cliente (WhatsApp, derivaciones, IA y
 * costos estimados) en bloques independientes. Solo lectura; separado del
 * consumo comercial. Sin rango elegido, el backend usa los últimos 30 días.
 */
export function AdminOperationalMetricsSection({ businessId }: { businessId: number }) {
    const [range, setRange] = useState<MetricsRange>({});
    const invalid = rangeError(range);
    const query = useAdminOperationalMetrics(businessId, range, invalid === null);
    const period = query.data?.period;

    const onSelect = (next?: DateRange) => setRange({
        date_from: next?.from ? localDateToString(next.from) : undefined,
        date_to: next?.to ? localDateToString(next.to) : undefined,
    });
    const shownFrom = range.date_from ?? period?.date_from;
    const shownTo = range.date_to ?? period?.date_to;

    let body: React.ReactNode;
    if (invalid) {
        body = <p role="alert" className="text-sm text-amber-800">{invalid}</p>;
    } else if (query.isLoading) {
        body = <p aria-busy="true" className="text-sm text-slate-500">Cargando métricas…</p>;
    } else if (query.isError || !query.data) {
        body = <p role="status" className="text-sm text-slate-600">{errorText(query.error)}</p>;
    } else {
        const m = query.data;
        body = (
            <div className="space-y-6">
                <p className="text-xs text-slate-500">
                    Del {formatDateAR(m.period.date_from)} al {formatDateAR(m.period.date_to)} ({m.period.days} días, {m.period.timezone}).
                    Los bloques no se suman entre sí y no indican el estado actual de la conexión.
                </p>
                <WhatsAppBlock w={m.whatsapp} />
                <HandoffBlock w={m.whatsapp} />
                <AIBlock a={m.openai_activity} />
                <CostBlock c={m.openai_costs} executions={m.openai_activity.executions} />
                <CoverageBlock m={m} />
            </div>
        );
    }

    return (
        <SectionCard
            title="Métricas operativas"
            description={`Actividad registrada del agente. Máximo ${MAX_RANGE_DAYS} días; por defecto, los últimos 30.`}
        >
            <div className="space-y-4">
                <DateRangePicker
                    from={shownFrom ? parseDateOnly(shownFrom) : undefined}
                    to={shownTo ? parseDateOnly(shownTo) : undefined}
                    onSelect={onSelect}
                    className="w-fit"
                />
                {body}
            </div>
        </SectionCard>
    );
}
