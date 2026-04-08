'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import type { Route } from 'next';
import { getReviewStats, getReviewSettings } from '@/features/reviews/api';
import type { ReviewStats, ReviewConfig } from '@/features/reviews/types';
import { SMART_FILTER, CTA_PRIMARY } from '@/features/reviews/product';

/* ── Labels & colors ───────────────────────────────────────── */

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

const STATUS_BADGE_COLORS: Record<string, string> = {
    new: 'bg-blue-100 text-blue-700',
    read: 'bg-slate-100 text-slate-600',
    contacted: 'bg-amber-100 text-amber-700',
    resolved: 'bg-green-100 text-green-700',
};

const RATING_COLORS: Record<string, string> = {
    '5': 'bg-green-500',
    '4': 'bg-emerald-400',
    '3': 'bg-yellow-400',
    '2': 'bg-orange-400',
    '1': 'bg-red-400',
};

/* ── Component ─────────────────────────────────────────────── */

export function ReviewsDashboardClient() {
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
                if (!s && !c) {
                    setError('Error al cargar las estadísticas.');
                } else {
                    setStats(s);
                    setConfig(c);
                }
            })
            .finally(() => setLoading(false));
    }, []);

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

    const hasData = (stats?.total_reviews ?? 0) > 0;

    /* ── Compute config warnings ───────────────────────────── */
    const warnings: string[] = [];
    if (config && !config.enabled) {
        warnings.push('Las reseñas están desactivadas. Activálas desde Configuración para empezar a recibir opiniones.');
    }
    if (config && !config.redirect_url) {
        warnings.push('No tenés una URL de redirección configurada. Las calificaciones altas no se derivarán a Google.');
    }

    return (
        <div className="space-y-6">
            {/* ── Config warnings ──────────────────────────────── */}
            {warnings.map((msg, i) => (
                <div key={i} className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
                    <span className="mt-0.5 shrink-0 text-amber-500">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                    </span>
                    <div className="flex-1">
                        <p className="text-sm text-amber-800">{msg}</p>
                        <Link
                            href={'/app/resenas/configuracion' as Route}
                            className="mt-1 inline-block text-xs font-semibold text-amber-700 underline underline-offset-2 hover:text-amber-900"
                        >
                            Ir a Configuración →
                        </Link>
                    </div>
                </div>
            ))}

            {/* ── Channel status ───────────────────────────────── */}
            {config && (
                <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                    <h3 className="text-sm font-semibold text-slate-700 mb-3">Estado del canal</h3>
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                        <StatusPill
                            label="Reseñas"
                            active={config.enabled}
                            activeText="Activas"
                            inactiveText="Desactivadas"
                        />
                        <StatusPill
                            label="Google"
                            active={!!config.redirect_url}
                            activeText="Conectado"
                            inactiveText="Sin configurar"
                        />
                        <div className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2">
                            <span className="text-xs text-slate-500">Umbral</span>
                            <span className="text-sm font-semibold text-slate-700">≥ {config.redirect_threshold}★ → Google</span>
                        </div>
                        <StatusPill
                            label="Contacto"
                            active={config.collect_contact}
                            activeText="Se recopila"
                            inactiveText="No se pide"
                        />
                    </div>
                </div>
            )}

            {/* ── Empty state ──────────────────────────────────── */}
            {!hasData && (
                <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center space-y-3">
                    <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-slate-100">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-7 w-7 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                        </svg>
                    </div>
                    <p className="font-semibold text-slate-700">Todavía no hay reseñas</p>
                    <p className="text-sm text-slate-500">
                        Compartí tu QR con tus clientes para empezar a recibir opiniones.
                    </p>
                    <Link
                        href={CTA_PRIMARY.href as Route}
                        className="mt-2 inline-block rounded-full bg-brand-600 px-5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-brand-700 transition-colors"
                    >
                        {CTA_PRIMARY.label}
                    </Link>
                </div>
            )}

            {/* ── Smart filter — diferenciador clave ───────────── */}
            <div className="rounded-2xl border border-indigo-100 bg-indigo-50/30 p-5 space-y-3">
                <h3 className="text-sm font-bold text-slate-800">{SMART_FILTER.headline}</h3>
                <p className="text-xs text-slate-600">{SMART_FILTER.description}</p>
                <div className="grid gap-2 sm:grid-cols-2">
                    {SMART_FILTER.bullets.map((b) => (
                        <div key={b.label} className="flex items-center gap-2 rounded-lg bg-white p-2.5 border border-indigo-100">
                            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-[10px] font-bold text-indigo-700">
                                {b.label.startsWith('≥') ? '★' : '☆'}
                            </span>
                            <div className="text-xs">
                                <p className="font-semibold text-slate-700">{b.label}</p>
                                <p className="text-slate-500">{b.result}</p>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* ── KPI Cards ─────────────────────────────────────── */}
            {hasData && stats && (<>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <KpiCard
                    label="Total reseñas"
                    value={stats.total_reviews}
                    icon={<StarIcon />}
                />
                <KpiCard
                    label="Promedio"
                    value={stats.average_rating.toFixed(1)}
                    suffix="/ 5"
                    icon={<TrendUpIcon />}
                    highlight={stats.average_rating >= 4}
                />
                <KpiCard
                    label="Visitas al QR"
                    value={stats.total_visits}
                    icon={<EyeIcon />}
                />
                <KpiCard
                    label="Conversión"
                    value={`${stats.conversion_rate}%`}
                    icon={<TargetIcon />}
                    highlight={stats.conversion_rate >= 30}
                />
            </div>

            {/* ── Quality + Operations ──────────────────────────── */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <KpiCard
                    label="Positivas (≥4★)"
                    value={stats.positive_reviews}
                    suffix={`(${stats.positive_rate}%)`}
                    color="text-green-600"
                />
                <KpiCard
                    label="Negativas (≤3★)"
                    value={stats.negative_reviews}
                    suffix={`(${stats.negative_rate}%)`}
                    color="text-red-500"
                />
                <KpiCard
                    label="Nuevas / sin leer"
                    value={stats.new_reviews}
                    color={stats.new_reviews > 0 ? 'text-blue-600' : undefined}
                />
                <KpiCard
                    label="Tasa resolución"
                    value={`${stats.resolution_rate}%`}
                    suffix={`(${stats.resolved_reviews} resueltas)`}
                    highlight={stats.resolution_rate >= 70}
                />
            </div>

            {/* ── Trend + Distributions ─────────────────────────── */}
            <div className="grid gap-6 lg:grid-cols-2">
                {/* Rating distribution */}
                <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                    <h3 className="text-sm font-semibold text-slate-700">Distribución por estrellas</h3>
                    <div className="space-y-2">
                        {[5, 4, 3, 2, 1].map((star) => {
                            const count = stats.rating_distribution[String(star)] ?? 0;
                            const pct = stats.total_reviews > 0
                                ? Math.round((count / stats.total_reviews) * 100)
                                : 0;
                            return (
                                <div key={star} className="flex items-center gap-3 text-sm">
                                    <span className="w-12 text-right text-slate-600 font-medium">
                                        {star} ★
                                    </span>
                                    <div className="flex-1 h-3 rounded-full bg-slate-100 overflow-hidden">
                                        <div
                                            className={`h-full rounded-full ${RATING_COLORS[String(star)]} transition-all duration-500`}
                                            style={{ width: `${pct}%` }}
                                        />
                                    </div>
                                    <span className="w-14 text-right text-xs text-slate-500">
                                        {count} ({pct}%)
                                    </span>
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Status distribution */}
                <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                    <h3 className="text-sm font-semibold text-slate-700">Pipeline operativo</h3>
                    <div className="space-y-2">
                        {(['new', 'read', 'contacted', 'resolved'] as const).map((st) => {
                            const count = stats.status_distribution[st] ?? 0;
                            const pct = stats.total_reviews > 0
                                ? Math.round((count / stats.total_reviews) * 100)
                                : 0;
                            return (
                                <div key={st} className="flex items-center gap-3 text-sm">
                                    <span className="w-24 text-right text-slate-600 font-medium">
                                        {STATUS_LABELS[st]}
                                    </span>
                                    <div className="flex-1 h-3 rounded-full bg-slate-100 overflow-hidden">
                                        <div
                                            className={`h-full rounded-full ${STATUS_COLORS[st]} transition-all duration-500`}
                                            style={{ width: `${pct}%` }}
                                        />
                                    </div>
                                    <span className="w-14 text-right text-xs text-slate-500">
                                        {count} ({pct}%)
                                    </span>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>

            {/* ── Trend cards ──────────────────────────────────── */}
            <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm flex items-center gap-4">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                        <CalendarIcon />
                    </div>
                    <div>
                        <p className="text-2xl font-bold text-slate-900">{stats.reviews_last_7_days}</p>
                        <p className="text-xs text-slate-500">Reseñas últimos 7 días</p>
                    </div>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm flex items-center gap-4">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                        <CalendarIcon />
                    </div>
                    <div>
                        <p className="text-2xl font-bold text-slate-900">{stats.reviews_last_30_days}</p>
                        <p className="text-xs text-slate-500">Reseñas últimos 30 días</p>
                    </div>
                </div>
            </div>

            {/* ── Recent reviews ───────────────────────────────── */}
            {stats.recent_reviews.length > 0 && (
                <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                    <div className="flex items-center justify-between">
                        <h3 className="text-sm font-semibold text-slate-700">Actividad reciente</h3>
                        <Link
                            href={'/app/resenas/feedback' as Route}
                            className="text-xs font-medium text-brand-600 hover:text-brand-700"
                        >
                            Ver todo →
                        </Link>
                    </div>
                    <div className="divide-y divide-slate-100">
                        {stats.recent_reviews.map((review) => (
                            <div key={review.id} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
                                {/* Stars */}
                                <div className="flex gap-0.5 shrink-0 pt-0.5">
                                    {[1, 2, 3, 4, 5].map((s) => (
                                        <svg
                                            key={s}
                                            xmlns="http://www.w3.org/2000/svg"
                                            className={`h-3.5 w-3.5 ${s <= review.rating ? 'text-yellow-400' : 'text-slate-200'}`}
                                            fill={s <= review.rating ? 'currentColor' : 'none'}
                                            viewBox="0 0 24 24"
                                            stroke="currentColor"
                                            strokeWidth={s <= review.rating ? 0 : 1.5}
                                        >
                                            <path strokeLinecap="round" strokeLinejoin="round" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                                        </svg>
                                    ))}
                                </div>

                                {/* Content */}
                                <div className="flex-1 min-w-0">
                                    {review.comment ? (
                                        <p className="text-sm text-slate-700 line-clamp-2">{review.comment}</p>
                                    ) : (
                                        <p className="text-sm text-slate-400 italic">Sin comentario</p>
                                    )}
                                    <p className="mt-0.5 text-xs text-slate-400">
                                        {new Date(review.created_at).toLocaleDateString('es-AR', {
                                            day: 'numeric',
                                            month: 'short',
                                        })}
                                        {' · '}
                                        {review.source === 'qr' ? 'QR' : review.source === 'menu' ? 'Menú' : 'Directo'}
                                    </p>
                                </div>

                                {/* Status badge */}
                                <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${STATUS_BADGE_COLORS[review.status] ?? 'bg-slate-100 text-slate-500'}`}>
                                    {STATUS_LABELS[review.status] ?? review.status}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
            </>)}
        </div>
    );
}

/* ── Status pill ───────────────────────────────────────────── */

function StatusPill({
    label,
    active,
    activeText,
    inactiveText,
}: {
    label: string;
    active: boolean;
    activeText: string;
    inactiveText: string;
}) {
    return (
        <div className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2">
            <span className={`h-2 w-2 rounded-full ${active ? 'bg-green-500' : 'bg-slate-300'}`} />
            <span className="text-xs text-slate-500">{label}</span>
            <span className={`ml-auto text-sm font-semibold ${active ? 'text-green-700' : 'text-slate-400'}`}>
                {active ? activeText : inactiveText}
            </span>
        </div>
    );
}

/* ── KPI Card ──────────────────────────────────────────────── */

function KpiCard({
    label,
    value,
    suffix,
    icon,
    highlight,
    color,
}: {
    label: string;
    value: string | number;
    suffix?: string;
    icon?: React.ReactNode;
    highlight?: boolean;
    color?: string;
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
                {suffix && (
                    <span className="ml-1 text-sm font-normal text-slate-400">{suffix}</span>
                )}
            </p>
        </div>
    );
}

/* ── Icons (inline SVG — no external deps) ─────────────────── */

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
            <circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="6" /><circle cx="12" cy="12" r="2" />
        </svg>
    );
}

function CalendarIcon() {
    return (
        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
    );
}
