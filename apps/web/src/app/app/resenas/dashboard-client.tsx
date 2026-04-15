'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import type { Route } from 'next';
import { useSearchParams } from 'next/navigation';
import { getReviewStats, getReviewSettings, activateReviewsTrial } from '@/features/reviews/api';
import type { ReviewStats, ReviewConfig } from '@/features/reviews/types';
import { CTA_PRIMARY } from '@/features/reviews/product';
import { UpgradeToProButton } from '@/features/reviews/upgrade-to-pro-button';
import { UpgradeSuccessBanner } from '@/features/reviews/upgrade-success-banner';

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

const PLAN_BADGE: Record<string, { label: string; cls: string }> = {
    pro:   { label: 'Pro',   cls: 'bg-green-100 text-green-800 ring-green-600/20' },
    trial: { label: 'Trial', cls: 'bg-indigo-100 text-indigo-800 ring-indigo-600/20' },
    base:  { label: 'Base',  cls: 'bg-slate-100 text-slate-700 ring-slate-500/10' },
};

/* ── Component ─────────────────────────────────────────────── */

export function ReviewsDashboardClient() {
    const searchParams = useSearchParams();
    const upgradeParam = searchParams.get('upgrade');

    const [stats, setStats] = useState<ReviewStats | null>(null);
    const [config, setConfig] = useState<ReviewConfig | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [activatingTrial, setActivatingTrial] = useState(false);

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
                <p className="text-sm text-slate-400 animate-pulse">Cargando dashboard…</p>
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

    /* ── Derived state ──────────────────────────────── */
    const hasData = (stats?.total_reviews ?? 0) > 0;
    const isSmartFilter = config?.effective_mode === 'smart_filter';
    const threshold = config?.redirect_threshold ?? 4;
    const newFeedbackCount = stats?.new_reviews ?? 0;
    const showTrialCta = config != null && !config.smart_filter_allowed && config.trial_available;
    const isPostTrial = config != null && config.trial_used && !config.trial_active && !config.smart_filter_allowed;
    const trialFeedbackCount = stats?.negative_reviews ?? 0;
    const isPro = config?.is_reviews_pro ?? false;
    const planKey = isPro ? 'pro' : config?.trial_active ? 'trial' : 'base';
    const plan = PLAN_BADGE[planKey];

    async function handleActivateTrial() {
        setActivatingTrial(true);
        try {
            const updated = await activateReviewsTrial();
            setConfig(updated);
        } catch {
            setError('No se pudo activar el período de prueba.');
        } finally {
            setActivatingTrial(false);
        }
    }

    /* ── Compute config warnings ───────────────────────── */
    const warnings: string[] = [];
    if (config && !config.enabled) {
        warnings.push('Las reseñas están desactivadas. Activalas desde Configuración para empezar a recibir opiniones.');
    }
    if (config && !config.redirect_url) {
        warnings.push('No tenés una URL de redirección configurada. Las reseñas no se derivarán a Google.');
    }

    const hasAlerts = !!(upgradeParam || (config?.trial_active && config.trial_ends_at)
        || (isSmartFilter && newFeedbackCount > 0) || warnings.length > 0);

    return (
        <div className="space-y-5">
            {/* â•â•â• 1. PRODUCT STATUS STRIP â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• */}
            {config && (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-xl border border-slate-200 bg-white px-4 py-2.5 shadow-sm">
                    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold ring-1 ring-inset ${plan.cls}`}>
                        {plan.label}
                    </span>
                    <Sep />
                    <span className="text-sm text-slate-600">
                        {isSmartFilter ? 'Filtro inteligente' : 'Modo directo'}
                    </span>
                    {isSmartFilter && (
                        <>
                            <Sep />
                            <span className="text-xs text-slate-500">≥{threshold}★ → Google</span>
                        </>
                    )}
                    <Sep />
                    <StatusDot active={config.enabled} label={config.enabled ? 'Activo' : 'Desactivado'} />
                    {config.redirect_url && (
                        <>
                            <Sep />
                            <StatusDot active label="Google" />
                        </>
                    )}
                    {planKey === 'trial' && config.trial_ends_at && (() => {
                        const daysLeft = Math.max(0, Math.ceil((new Date(config.trial_ends_at).getTime() - Date.now()) / 86_400_000));
                        return (
                            <>
                                <Sep />
                                <span className="text-xs font-medium text-indigo-600">
                                    {daysLeft === 0 ? 'Vence hoy' : `${daysLeft}d restante${daysLeft === 1 ? '' : 's'}`}
                                </span>
                            </>
                        );
                    })()}
                </div>
            )}

            {/* â•â•â• 2. CONTEXTUAL ALERTS (tight spacing) â•â•â•â•â•â• */}
            {hasAlerts && (
                <div className="space-y-2">
                    {upgradeParam === 'success' && (
                        <UpgradeSuccessBanner
                            initialConfig={config}
                            onUpgradeConfirmed={(cfg) => {
                                setConfig(cfg);
                                getReviewStats().then(setStats).catch(() => null);
                            }}
                        />
                    )}
                    {upgradeParam === 'failure' && (
                        <AlertBanner variant="error" title="El pago no se completó" description="Podés intentar de nuevo cuando quieras desde el botón de upgrade." />
                    )}
                    {upgradeParam === 'pending' && (
                        <AlertBanner variant="warning" title="Tu pago está pendiente de confirmación" description="Una vez que se acredite, tu plan se actualizará automáticamente." />
                    )}
                    {config?.trial_active && config.trial_ends_at && (() => {
                        const daysLeft = Math.max(0, Math.ceil((new Date(config.trial_ends_at).getTime() - Date.now()) / 86_400_000));
                        return (
                            <AlertBanner
                                variant="info"
                                title={`Trial de filtro inteligente — ${daysLeft === 0 ? 'vence hoy' : `${daysLeft} día${daysLeft === 1 ? '' : 's'} restante${daysLeft === 1 ? '' : 's'}`}`}
                                description="Upgrade a Pro para mantener el filtro inteligente y el feedback privado."
                            />
                        );
                    })()}
                    {isSmartFilter && newFeedbackCount > 0 && (
                        <AlertBanner
                            variant="action"
                            title={newFeedbackCount === 1 ? 'Tenés 1 opinión nueva sin leer' : `Tenés ${newFeedbackCount} opiniones nuevas sin leer`}
                            linkHref="/app/resenas/feedback"
                            linkLabel="Ver feedback →"
                        />
                    )}
                    {warnings.map((msg, i) => (
                        <AlertBanner key={i} variant="warning" title={msg} linkHref="/app/resenas/configuracion" linkLabel="Ir a Configuración →" />
                    ))}
                </div>
            )}

            {/* â•â•â• 3. CTAs (post-trial / trial activation) â•â•â• */}
            {isPostTrial && (
                <div className="rounded-2xl border border-slate-200 bg-gradient-to-r from-slate-50 to-white p-6 shadow-sm space-y-3">
                    <h3 className="text-sm font-bold text-slate-900">Tu período de prueba finalizó</h3>
                    <p className="text-sm text-slate-600">
                        Tu QR volvió al modo Directo: todas las reseñas se redirigen a Google.
                        {trialFeedbackCount > 0 && (
                            <> Durante la prueba, capturaste <span className="font-semibold">{trialFeedbackCount} opinión{trialFeedbackCount === 1 ? '' : 'es'}</span> como feedback privado.</>
                        )}
                    </p>
                    <p className="text-xs text-slate-500">
                        Activá el plan Pro para recuperar el filtro inteligente y seguir gestionando opiniones.
                    </p>
                    <UpgradeToProButton />
                </div>
            )}
            {showTrialCta && (
                <div className="rounded-2xl border border-indigo-200 bg-gradient-to-r from-indigo-50 to-white p-6 shadow-sm space-y-3">
                    <h3 className="text-sm font-bold text-indigo-900">Probá el Filtro Inteligente — 7 días gratis</h3>
                    <p className="text-sm text-indigo-700">
                        Activá la prueba y tu QR empieza a filtrar: las reseñas altas van a Google y las bajas te llegan como feedback privado.
                    </p>
                    <button
                        onClick={handleActivateTrial}
                        disabled={activatingTrial}
                        className="rounded-full bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 transition-colors disabled:opacity-50"
                    >
                        {activatingTrial ? 'Activando…' : 'Activar prueba gratuita'}
                    </button>
                </div>
            )}

            {/* â•â•â• 4. QUICK ACTIONS â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• */}
            <div className="flex flex-wrap gap-2">
                <QuickAction href={CTA_PRIMARY.href} label={CTA_PRIMARY.label} primary />
                {isSmartFilter && <QuickAction href="/app/resenas/feedback" label="Ver feedback" />}
                {isPro && <QuickAction href="/app/resenas/analytics" label="Analytics" />}
                <QuickAction href="/app/resenas/configuracion" label="Configuración" />
            </div>

            {/* â•â•â• 5. EMPTY STATE â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• */}
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

            {/* â•â•â• 6. DATA SECTIONS â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• */}
            {hasData && stats && (<>
                {/* ── Métricas ──────────────────────────────── */}
                <SectionHeading title="Métricas" />
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    <KpiCard label="Total reseñas" value={stats.total_reviews} icon={<StarIcon />} />
                    <KpiCard
                        label="Promedio"
                        value={stats.average_rating.toFixed(1)}
                        suffix="/ 5"
                        icon={<TrendUpIcon />}
                        highlight={stats.average_rating >= threshold}
                    />
                    <KpiCard label="Visitas al QR" value={stats.total_visits} icon={<EyeIcon />} />
                    <KpiCard
                        label="Conversión"
                        value={`${stats.conversion_rate}%`}
                        icon={<TargetIcon />}
                        highlight={stats.conversion_rate >= 30}
                    />
                    <KpiCard label="Últimos 7 días" value={stats.reviews_last_7_days} icon={<CalendarIcon />} />
                    <KpiCard label="Últimos 30 días" value={stats.reviews_last_30_days} icon={<CalendarIcon />} />
                </div>

                {/* ── Operaciones (smart_filter only) ──────── */}
                {isSmartFilter && (<>
                    <SectionHeading title="Operaciones" />
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                        <KpiCard
                            label={`Positivas (≥${threshold}★)`}
                            value={stats.positive_reviews}
                            suffix={`(${stats.positive_rate}%)`}
                            color="text-green-600"
                        />
                        <KpiCard
                            label={`Negativas (<${threshold}★)`}
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
                </>)}

                {/* ── Distribución ─────────────────────────── */}
                <SectionHeading title="Distribución" />
                <div className="grid gap-5 lg:grid-cols-2">
                    {/* Rating distribution */}
                    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                        <h3 className="text-sm font-semibold text-slate-700">
                            Por estrellas
                            {isSmartFilter && <span className="ml-1 text-xs font-normal text-slate-400">(umbral ≥{threshold}★)</span>}
                        </h3>
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

                    {/* Status distribution (smart_filter only) */}
                    {isSmartFilter && (
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
                    )}
                </div>

                {/* ── Actividad reciente (smart_filter only) ── */}
                {isSmartFilter && stats.recent_reviews.length > 0 && (<>
                    <SectionHeading
                        title="Actividad reciente"
                        action={
                            <Link
                                href={'/app/resenas/feedback' as Route}
                                className="text-xs font-medium text-brand-600 hover:text-brand-700"
                            >
                                Ver todo →
                            </Link>
                        }
                    />
                    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
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
                </>)}
            </>)}
        </div>
    );
}

/* ── Tiny helpers ──────────────────────────────────────────── */

function Sep() {
    return <span className="text-slate-300" aria-hidden>·</span>;
}

function StatusDot({ active, label }: { active: boolean; label: string }) {
    return (
        <span className={`inline-flex items-center gap-1.5 text-xs ${active ? 'text-green-700' : 'text-slate-400'}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${active ? 'bg-green-500' : 'bg-slate-300'}`} />
            {label}
        </span>
    );
}

function SectionHeading({ title, action }: { title: string; action?: React.ReactNode }) {
    return (
        <div className="flex items-center justify-between pt-1">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">{title}</h2>
            {action}
        </div>
    );
}

function QuickAction({ href, label, primary }: { href: string; label: string; primary?: boolean }) {
    return (
        <Link
            href={href as Route}
            className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-colors ${
                primary
                    ? 'bg-brand-600 text-white shadow-sm hover:bg-brand-700'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-800'
            }`}
        >
            {label}
        </Link>
    );
}

/* ── AlertBanner ───────────────────────────────────────────── */

function AlertBanner({ variant, title, description, linkHref, linkLabel }: {
    variant: 'error' | 'warning' | 'info' | 'action';
    title: string;
    description?: string;
    linkHref?: string;
    linkLabel?: string;
}) {
    const STYLES = {
        error:   { border: 'border-red-200',    bg: 'bg-red-50',    icon: 'text-red-500',    titleCls: 'text-red-800',    desc: 'text-red-600',    link: 'text-red-700 hover:text-red-900' },
        warning: { border: 'border-amber-200',  bg: 'bg-amber-50',  icon: 'text-amber-500',  titleCls: 'text-amber-800',  desc: 'text-amber-600',  link: 'text-amber-700 hover:text-amber-900' },
        info:    { border: 'border-indigo-200', bg: 'bg-indigo-50', icon: 'text-indigo-500', titleCls: 'text-indigo-800', desc: 'text-indigo-600', link: 'text-indigo-700 hover:text-indigo-900' },
        action:  { border: 'border-blue-200',   bg: 'bg-blue-50',   icon: 'text-blue-500',   titleCls: 'text-blue-800',   desc: 'text-blue-600',   link: 'text-blue-700 hover:text-blue-900' },
    };
    const ICONS = {
        error:   'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
        warning: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
        info:    'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
        action:  'M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9',
    };
    const s = STYLES[variant];
    return (
        <div className={`flex items-start gap-3 rounded-xl border ${s.border} ${s.bg} px-4 py-3`}>
            <span className={`mt-0.5 shrink-0 ${s.icon}`}>
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d={ICONS[variant]} />
                </svg>
            </span>
            <div className="flex-1">
                <p className={`text-sm font-semibold ${s.titleCls}`}>{title}</p>
                {description && <p className={`text-xs ${s.desc}`}>{description}</p>}
                {linkHref && linkLabel && (
                    <Link href={linkHref as Route} className={`mt-1 inline-block text-xs font-semibold underline underline-offset-2 ${s.link}`}>
                        {linkLabel}
                    </Link>
                )}
            </div>
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

