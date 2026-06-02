'use client';

import { useState, useEffect, useCallback } from 'react';
import { getReviews, updateReviewStatus, getReviewSettings, getReviewStats, activateReviewsTrial } from '@/features/reviews/api';
import type { Review, ReviewStatus, ReviewConfig, ReviewStats } from '@/features/reviews/types';
import { UpgradeToProButton } from '@/features/reviews/upgrade-to-pro-button';

const STATUS_LABELS: Record<ReviewStatus, string> = {
    new: 'Nuevo',
    read: 'Leído',
    contacted: 'Contactado',
    resolved: 'Resuelto',
};

const STATUS_COLORS: Record<ReviewStatus, string> = {
    new: 'bg-blue-100 text-blue-700',
    read: 'bg-slate-100 text-slate-600',
    contacted: 'bg-amber-100 text-amber-700',
    resolved: 'bg-green-100 text-green-700',
};

/** Valid next states from each status. */
const STATUS_TRANSITIONS: Record<ReviewStatus, { target: ReviewStatus; label: string }[]> = {
    new: [{ target: 'read', label: 'Marcar leído' }],
    read: [{ target: 'contacted', label: 'Marcar contactado' }],
    contacted: [{ target: 'resolved', label: 'Marcar resuelto' }],
    resolved: [{ target: 'read', label: 'Reabrir' }],
};

export function FeedbackClient() {
    const [reviews, setReviews] = useState<Review[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [filterStatus, setFilterStatus] = useState<string>('');
    const [filterRating, setFilterRating] = useState<string>('');
    const [ordering, setOrdering] = useState('-created_at');
    const [config, setConfig] = useState<ReviewConfig | null>(null);
    const [configLoading, setConfigLoading] = useState(true);
    const [activatingTrial, setActivatingTrial] = useState(false);
    const [transitioningId, setTransitioningId] = useState<string | null>(null);
    const [cardErrors, setCardErrors] = useState<Record<string, string>>({});
    const [stats, setStats] = useState<ReviewStats | null>(null);

    useEffect(() => {
        Promise.all([
            getReviewSettings().catch(() => null),
            getReviewStats().catch(() => null),
        ])
            .then(([c, s]) => { setConfig(c); setStats(s); })
            .finally(() => setConfigLoading(false));
    }, []);

    const fetchReviews = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            const data = await getReviews({
                status: filterStatus || undefined,
                rating: filterRating || undefined,
                ordering: ordering || undefined,
            });
            setReviews(data);
        } catch {
            setError('Error al cargar las reseñas.');
        } finally {
            setLoading(false);
        }
    }, [filterStatus, filterRating, ordering]);

    useEffect(() => {
        fetchReviews();
    }, [fetchReviews]);

    async function handleStatusChange(id: string, newStatus: ReviewStatus) {
        setTransitioningId(id);
        setCardErrors((prev) => { const next = { ...prev }; delete next[id]; return next; });
        try {
            const updated = await updateReviewStatus(id, newStatus);
            setReviews((prev) => prev.map((r) => (r.id === id ? updated : r)));
            window.dispatchEvent(new CustomEvent('reviews-updated'));
        } catch {
            setCardErrors((prev) => ({ ...prev, [id]: 'Error al actualizar el estado.' }));
        } finally {
            setTransitioningId(null);
        }
    }

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

    function renderStars(rating: number) {
        return (
            <div className="flex gap-0.5">
                {[1, 2, 3, 4, 5].map((star) => (
                    <svg
                        key={star}
                        xmlns="http://www.w3.org/2000/svg"
                        className={`h-4 w-4 ${star <= rating ? 'text-yellow-400' : 'text-slate-200'}`}
                        fill={star <= rating ? 'currentColor' : 'none'}
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={star <= rating ? 0 : 1.5}
                    >
                        <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"
                        />
                    </svg>
                ))}
            </div>
        );
    }

    return (
        <>
            <header>
                <p className="text-xs font-semibold uppercase tracking-wide text-brand-500">
                    QR de Reseñas
                </p>
                <h1 className="text-3xl font-display font-bold text-slate-900">Feedback</h1>
                <p className="mt-1 text-sm text-slate-500">
                    Reseñas internas recibidas de tus clientes.
                </p>
            </header>

            {/* ── Gating: smart_filter not available ─────────── */}
            {!configLoading && config && !config.smart_filter_allowed && (() => {
                const isPostTrial = config.trial_used && !config.trial_active;
                const feedbackCount = stats?.negative_reviews ?? 0;

                return (
                <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center space-y-4 shadow-sm">
                    <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-slate-100">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-7 w-7 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            {isPostTrial
                                ? <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                                : <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                            }
                        </svg>
                    </div>
                    {isPostTrial ? (
                        <>
                            <h2 className="text-lg font-bold text-slate-900">Tu período de prueba finalizó</h2>
                            <p className="text-sm text-slate-500 max-w-sm mx-auto">
                                El filtro inteligente ya no está activo y tu QR volvió al modo Directo.
                                {feedbackCount > 0 && (
                                    <> Las <span className="font-semibold text-slate-700">{feedbackCount} opinión{feedbackCount === 1 ? '' : 'es'}</span> que capturaste durante la prueba siguen guardadas.</>
                                )}
                                {' '}Activá el plan Pro para recuperar el feedback privado.
                            </p>
                        </>
                    ) : (
                        <>
                            <h2 className="text-lg font-bold text-slate-900">Feedback disponible con el Filtro Inteligente</h2>
                            <p className="text-sm text-slate-500 max-w-sm mx-auto">
                                El módulo de feedback recopila reseñas internas cuando el filtro inteligente está activo.
                                {config.trial_available
                                    ? ' Activá la prueba gratuita de 7 días para empezar.'
                                    : ' Upgrade a Pro para recibir y gestionar opiniones de tus clientes.'
                                }
                            </p>
                        </>
                    )}
                    {config.trial_available ? (
                        <button
                            onClick={handleActivateTrial}
                            disabled={activatingTrial}
                            className="inline-block rounded-full bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 transition-colors disabled:opacity-50"
                        >
                            {activatingTrial ? 'Activando…' : 'Activar prueba gratuita'}
                        </button>
                    ) : (
                        <UpgradeToProButton />
                    )}
                </div>
                );
            })()}

            {/* ── Main content (only when accessible) ────────── */}
            {(configLoading || !config || config.smart_filter_allowed) && (() => {
                const isPro = config?.is_reviews_pro ?? false;
                return (
            <>
            <div className="flex flex-wrap gap-3">
                {isPro && (
                    <select
                        value={filterStatus}
                        onChange={(e) => setFilterStatus(e.target.value)}
                        className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                    >
                        <option value="">Todos los estados</option>
                        <option value="new">Nuevos</option>
                        <option value="read">Leídos</option>
                        <option value="contacted">Contactados</option>
                        <option value="resolved">Resueltos</option>
                    </select>
                )}

                <select
                    value={filterRating}
                    onChange={(e) => setFilterRating(e.target.value)}
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                >
                    <option value="">Todos los puntajes</option>
                    <option value="1">1 estrella</option>
                    <option value="2">2 estrellas</option>
                    <option value="3">3 estrellas</option>
                    <option value="4">4 estrellas</option>
                    <option value="5">5 estrellas</option>
                </select>

                <select
                    value={ordering}
                    onChange={(e) => setOrdering(e.target.value)}
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                >
                    <option value="-created_at">Más recientes</option>
                    <option value="created_at">Más antiguos</option>
                    <option value="-rating">Mayor puntaje</option>
                    <option value="rating">Menor puntaje</option>
                </select>
            </div>

            {!isPro && (
                <div className="rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-xs text-indigo-800">
                    Estás viendo el feedback privado básico.
                    {' '}
                    <span className="font-semibold">Activá Reseñas Pro</span>
                    {' '}
                    para gestionar estados (nuevo · leído · contactado · resuelto),
                    analytics avanzadas y métricas de conversión.
                </div>
            )}

            {error && <p className="text-sm text-red-600">{error}</p>}

            {loading ? (
                <div className="flex h-40 items-center justify-center">
                    <p className="text-sm text-slate-400">Cargando reseñas…</p>
                </div>
            ) : reviews.length === 0 ? (
                <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
                    <p className="text-slate-500">
                        No hay reseñas{filterStatus || filterRating ? ' con estos filtros' : ' todavía'}.
                    </p>
                </div>
            ) : (
                <div className="space-y-4">
                    {reviews.map((review) => (
                        <div
                            key={review.id}
                            className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-3"
                        >
                            <div className="flex items-start justify-between gap-4">
                                <div className="space-y-1">
                                    {renderStars(review.rating)}
                                    <p className="text-xs text-slate-400">
                                        {new Date(review.created_at).toLocaleDateString('es-AR', {
                                            day: 'numeric',
                                            month: 'short',
                                            year: 'numeric',
                                            hour: '2-digit',
                                            minute: '2-digit',
                                        })}
                                        {' · '}
                                        {review.source === 'qr' ? 'QR' : review.source === 'menu' ? 'Menú' : 'Directo'}
                                    </p>
                                </div>

                                {isPro && (
                                    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLORS[review.status]}`}>
                                        {STATUS_LABELS[review.status]}
                                    </span>
                                )}
                            </div>

                            {review.comment && (
                                <p className="text-sm text-slate-700">{review.comment}</p>
                            )}

                            {review.contact_info && (
                                <p className="text-xs text-slate-400">
                                    Contacto: <span className="text-slate-600">{review.contact_info}</span>
                                </p>
                            )}

                            {isPro && (
                                <div className="flex gap-2 pt-1">
                                    {STATUS_TRANSITIONS[review.status]?.map(({ target, label }) => (
                                        <button
                                            key={target}
                                            onClick={() => handleStatusChange(review.id, target)}
                                            disabled={transitioningId === review.id}
                                            className="rounded-full border border-slate-300 px-3 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors disabled:opacity-50 disabled:cursor-wait"
                                        >
                                            {transitioningId === review.id ? 'Guardando…' : label}
                                        </button>
                                    ))}
                                </div>
                            )}

                            {cardErrors[review.id] && (
                                <p className="text-xs text-red-600">{cardErrors[review.id]}</p>
                            )}
                        </div>
                    ))}
                </div>
            )}
            </>
                );
            })()}
        </>
    );
}
