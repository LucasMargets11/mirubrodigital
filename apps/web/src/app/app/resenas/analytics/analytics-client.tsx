'use client';

import { useState, useEffect, useMemo } from 'react';
import type { EChartsCoreOption } from 'echarts/core';
import { getReviewStats, getReviewSettings } from '@/features/reviews/api';
import type { ReviewStats, ReviewConfig } from '@/features/reviews/types';
import { EChart } from '@/lib/charts';
import {
    COLOR_PRIMARY,
    COLOR_AXIS_LABEL,
    COLOR_GRID_LINE,
    TOOLTIP_BASE_STYLE,
    primaryAreaGradient,
} from '@/lib/charts/theme';
import { UpgradeToProButton } from '@/features/reviews/upgrade-to-pro-button';

/* ── Color maps ────────────────────────────────────────────── */

const RATING_COLORS: Record<string, string> = {
    '5': 'bg-green-500',
    '4': 'bg-emerald-400',
    '3': 'bg-yellow-400',
    '2': 'bg-orange-400',
    '1': 'bg-red-400',
};

const STATUS_LABELS: Record<string, string> = {
    new: 'Nuevas',
    read: 'Leídas',
    contacted: 'Contactadas',
    resolved: 'Resueltas',
};

const STATUS_COLORS: Record<string, string> = {
    new: 'bg-blue-500',
    read: 'bg-slate-400',
    contacted: 'bg-amber-500',
    resolved: 'bg-green-500',
};

/* ── Chart option builder (pure, testable) ─────────────────── */

export function buildTrendOption(
    trend: { date: string; count: number }[],
): EChartsCoreOption {
    const dates = trend.map((d) =>
        new Date(d.date).toLocaleDateString('es-AR', { day: 'numeric', month: 'short' }),
    );
    const counts = trend.map((d) => d.count);
    const rawDates = trend.map((d) =>
        new Date(d.date).toLocaleDateString('es-AR', { weekday: 'short', day: 'numeric', month: 'short' }),
    );

    return {
        grid: { top: 16, right: 12, bottom: 28, left: 4, containLabel: true },
        tooltip: {
            ...TOOLTIP_BASE_STYLE,
            trigger: 'axis',
            axisPointer: { type: 'line', lineStyle: { color: COLOR_GRID_LINE, type: 'dashed' } },
            formatter(params: unknown) {
                const items = params as Array<{ dataIndex: number; value: number }>;
                if (!items?.length) return '';
                const idx = items[0].dataIndex;
                return `<div style="font-weight:600;color:#0f172a;margin-bottom:4px">${rawDates[idx]}</div>`
                    + `<div style="font-size:13px">${counts[idx]} reseña${counts[idx] !== 1 ? 's' : ''}</div>`;
            },
        },
        xAxis: {
            type: 'category',
            data: dates,
            axisLabel: { color: COLOR_AXIS_LABEL, fontSize: 10, margin: 10, interval: 6 },
            axisTick: { show: false },
            axisLine: { show: false },
            boundaryGap: false,
        },
        yAxis: {
            type: 'value',
            minInterval: 1,
            axisLabel: { color: COLOR_AXIS_LABEL, fontSize: 10 },
            axisTick: { show: false },
            axisLine: { show: false },
            splitLine: { lineStyle: { color: COLOR_GRID_LINE, type: 'dashed' } },
        },
        series: [
            {
                type: 'line',
                data: counts,
                smooth: true,
                symbol: 'circle',
                symbolSize: 4,
                showSymbol: false,
                emphasis: { focus: 'series', itemStyle: { borderWidth: 2, borderColor: '#fff' } },
                lineStyle: { width: 2, color: COLOR_PRIMARY },
                itemStyle: { color: COLOR_PRIMARY },
                areaStyle: { color: primaryAreaGradient() },
            },
        ],
    };
}

/* ── Component ─────────────────────────────────────────────── */

export function AnalyticsClient() {
    const [stats, setStats] = useState<ReviewStats | null>(null);
    const [config, setConfig] = useState<ReviewConfig | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        Promise.all([
            getReviewStats().catch(() => null),
            getReviewSettings().catch(() => null),
        ])
            .then(([s, c]) => {
                if (!s && !c) setError('Error al cargar las métricas.');
                else { setStats(s); setConfig(c); }
            })
            .finally(() => setLoading(false));
    }, []);

    const trendOption = useMemo(
        () => (stats?.daily_trend ? buildTrendOption(stats.daily_trend) : null),
        [stats?.daily_trend],
    );

    if (loading) {
        return (
            <div className="flex h-48 items-center justify-center rounded-2xl border border-slate-200 bg-white">
                <p className="text-sm text-slate-400 animate-pulse">Cargando analytics…</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-center">
                <p className="text-sm font-semibold text-red-700">{error}</p>
            </div>
        );
    }

    const isReviewsPro = config?.is_reviews_pro ?? false;

    // PR-A: Analytics avanzadas son Pro-only. Base ve un upsell.
    if (!isReviewsPro) {
        return (
            <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center space-y-4 shadow-sm">
                <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-indigo-100">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-7 w-7 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                    </svg>
                </div>
                <div className="space-y-1">
                    <p className="font-semibold text-slate-800">Analytics avanzadas son parte de Reseñas Pro</p>
                    <p className="text-sm text-slate-500">
                        Métricas de conversión, tendencias por día y distribución de estados están disponibles en el plan Pro.
                    </p>
                </div>
                <UpgradeToProButton />
            </div>
        );
    }

    const isSmartFilter = config?.effective_mode === 'smart_filter';
    const threshold = config?.redirect_threshold ?? 4;
    const hasData = (stats?.total_reviews ?? 0) > 0;

    if (!hasData) {
        return (
            <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center space-y-3 shadow-sm">
                <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-slate-100">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-7 w-7 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                </div>
                <p className="font-semibold text-slate-700">Sin datos todavía</p>
                <p className="text-sm text-slate-500">Las métricas se llenarán a medida que recibas reseñas.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* ── KPI summary ──────────────────────────────────── */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <Metric icon={<StarIcon />} label="Total reseñas" value={stats!.total_reviews} />
                <Metric icon={<TrendUpIcon />} label="Promedio" value={`${stats!.average_rating.toFixed(1)} / 5`} highlight={stats!.average_rating >= threshold} />
                <Metric icon={<EyeIcon />} label="Visitas al QR" value={stats!.total_visits} />
                <Metric icon={<TargetIcon />} label="Conversión" value={`${stats!.conversion_rate}%`} highlight={stats!.conversion_rate >= 30} />
            </div>

            {/* ── Smart-filter operational KPIs ──────────────────── */}
            {isSmartFilter && (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <Metric label={`Positivas (≥${threshold}★)`} value={stats!.positive_reviews} suffix={`${stats!.positive_rate}%`} color="text-green-600" />
                <Metric label={`Negativas (<${threshold}★)`} value={stats!.negative_reviews} suffix={`${stats!.negative_rate}%`} color="text-red-500" />
                <Metric label="Tasa resolución" value={`${stats!.resolution_rate}%`} suffix={`${stats!.resolved_reviews} resueltas`} highlight={stats!.resolution_rate >= 70} />
                <Metric label="Nuevas / sin leer" value={stats!.new_reviews} color={stats!.new_reviews > 0 ? 'text-blue-600' : undefined} />
            </div>
            )}

            {/* ── 30-day trend chart ───────────────────────────── */}
            {trendOption && (
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
                <h3 className="text-sm font-semibold text-slate-700">Evolución últimos 30 días</h3>
                <EChart option={trendOption} height={220} />
            </div>
            )}

            {/* ── Scans vs Feedback funnel ──────────────────────── */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                <h3 className="text-sm font-semibold text-slate-700">Embudo: Escaneos → Feedback</h3>
                <FunnelBar
                    items={[
                        {
                            label: 'Escaneos (visitas)',
                            value: stats!.total_visits,
                            color: 'bg-indigo-500',
                            pct: 100,
                        },
                        {
                            label: 'Reseñas recibidas',
                            value: stats!.total_reviews,
                            color: 'bg-violet-500',
                            pct: stats!.total_visits > 0 ? Math.round(stats!.total_reviews / stats!.total_visits * 100) : 0,
                        },
                        ...(isSmartFilter
                            ? [
                                {
                                    label: 'Feedback privado',
                                    value: stats!.negative_reviews,
                                    color: 'bg-amber-500',
                                    pct: stats!.total_visits > 0 ? Math.round(stats!.negative_reviews / stats!.total_visits * 100) : 0,
                                },
                                {
                                    label: 'Resueltas',
                                    value: stats!.resolved_reviews,
                                    color: 'bg-green-500',
                                    pct: stats!.total_visits > 0 ? Math.round(stats!.resolved_reviews / stats!.total_visits * 100) : 0,
                                },
                            ]
                            : []),
                    ]}
                />
            </div>

            {/* ── Period comparison ─────────────────────────────── */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <Metric label="Reseñas 7d" value={stats!.reviews_last_7_days} />
                <Metric label="Reseñas 30d" value={stats!.reviews_last_30_days} />
                <Metric label="Visitas 7d" value={stats!.visits_last_7_days} />
                <Metric label="Visitas 30d" value={stats!.visits_last_30_days} />
            </div>

            {/* ── Distributions ─────────────────────────────────── */}
            <div className={`grid gap-6 ${isSmartFilter ? 'lg:grid-cols-2' : ''}`}>
                {/* Rating distribution */}
                <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                    <h3 className="text-sm font-semibold text-slate-700">
                        Distribución por estrellas
                        {isSmartFilter && <span className="ml-1 text-xs font-normal text-slate-400">(umbral ≥{threshold}★)</span>}
                    </h3>
                    <div className="space-y-2">
                        {[5, 4, 3, 2, 1].map((star) => {
                            const count = stats!.rating_distribution[String(star)] ?? 0;
                            const pct = stats!.total_reviews > 0
                                ? Math.round((count / stats!.total_reviews) * 100)
                                : 0;
                            return (
                                <div key={star} className="flex items-center gap-3 text-sm">
                                    <span className="w-12 text-right text-slate-600 font-medium">{star} ★</span>
                                    <div className="flex-1 h-3 rounded-full bg-slate-100 overflow-hidden">
                                        <div
                                            className={`h-full rounded-full ${RATING_COLORS[String(star)]} transition-all duration-500`}
                                            style={{ width: `${pct}%` }}
                                        />
                                    </div>
                                    <span className="w-14 text-right text-xs text-slate-500">{count} ({pct}%)</span>
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Status distribution (smart_filter only) */}
                {isSmartFilter && (
                <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                    <h3 className="text-sm font-semibold text-slate-700">Pipeline operativo</h3>
                    <div className="space-y-2">
                        {(['new', 'read', 'contacted', 'resolved'] as const).map((st) => {
                            const count = stats!.status_distribution[st] ?? 0;
                            const pct = stats!.total_reviews > 0
                                ? Math.round((count / stats!.total_reviews) * 100)
                                : 0;
                            return (
                                <div key={st} className="flex items-center gap-3 text-sm">
                                    <span className="w-24 text-right text-slate-600 font-medium">{STATUS_LABELS[st]}</span>
                                    <div className="flex-1 h-3 rounded-full bg-slate-100 overflow-hidden">
                                        <div
                                            className={`h-full rounded-full ${STATUS_COLORS[st]} transition-all duration-500`}
                                            style={{ width: `${pct}%` }}
                                        />
                                    </div>
                                    <span className="w-14 text-right text-xs text-slate-500">{count} ({pct}%)</span>
                                </div>
                            );
                        })}
                    </div>
                </div>
                )}
            </div>
        </div>
    );
}

/* ── Metric card ───────────────────────────────────────────── */

function Metric({
    label,
    value,
    suffix,
    highlight,
    color,
    icon,
}: {
    label: string;
    value: string | number;
    suffix?: string;
    highlight?: boolean;
    color?: string;
    icon?: React.ReactNode;
}) {
    return (
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-center justify-between">
                <p className="text-xs font-medium text-slate-500">{label}</p>
                {icon && (
                    <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-50 text-slate-400">
                        {icon}
                    </span>
                )}
            </div>
            <p className={`mt-2 text-2xl font-bold ${color ?? (highlight ? 'text-green-600' : 'text-slate-900')}`}>
                {value}
                {suffix && <span className="ml-1 text-sm font-normal text-slate-400">{suffix}</span>}
            </p>
        </div>
    );
}

/* ── Funnel bars ───────────────────────────────────────────── */

function FunnelBar({
    items,
}: {
    items: { label: string; value: number; color: string; pct: number }[];
}) {
    const maxValue = Math.max(...items.map((i) => i.value), 1);
    return (
        <div className="space-y-3">
            {items.map((item) => {
                const barWidth = Math.max(Math.round((item.value / maxValue) * 100), 2);
                return (
                    <div key={item.label} className="space-y-1">
                        <div className="flex items-baseline justify-between text-sm">
                            <span className="text-slate-600">{item.label}</span>
                            <span className="font-semibold text-slate-800 tabular-nums">
                                {item.value.toLocaleString('es-AR')}
                                <span className="ml-1 text-xs font-normal text-slate-400">({item.pct}%)</span>
                            </span>
                        </div>
                        <div className="h-3 rounded-full bg-slate-100 overflow-hidden">
                            <div
                                className={`h-full rounded-full ${item.color} transition-all duration-500`}
                                style={{ width: `${barWidth}%` }}
                            />
                        </div>
                    </div>
                );
            })}
        </div>
    );
}

/* ── Icons ─────────────────────────────────────────────────── */

function StarIcon() {
    return (
        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
        </svg>
    );
}

function TrendUpIcon() {
    return (
        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
        </svg>
    );
}

function EyeIcon() {
    return (
        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
        </svg>
    );
}

function TargetIcon() {
    return (
        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <circle cx="12" cy="12" r="10" />
            <circle cx="12" cy="12" r="6" />
            <circle cx="12" cy="12" r="2" />
        </svg>
    );
}
