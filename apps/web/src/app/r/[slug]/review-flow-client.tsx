'use client';

import { useState, useEffect, useRef } from 'react';
import type { PublicReviewConfig, ReviewSubmitResponse } from '@/features/reviews/types';

/* ── Microcopy ─────────────────────────────────────────────── */

const RATING_LABELS: Record<number, string> = {
    1: 'Muy mala',
    2: 'Podría mejorar',
    3: 'Normal',
    4: 'Muy buena',
    5: 'Excelente 🙌',
};

const COPY = {
    ratingTitle: (name: string) => `¿Cómo fue tu experiencia en ${name}?`,
    ratingSubtitle: 'Tu opinión nos ayuda a mejorar 💛',
    feedbackTitle: 'Gracias por tu feedback 🙏',
    feedbackSubtitle: 'Queremos mejorar tu experiencia. ¿Nos contás qué pasó?',
    feedbackPlaceholder: 'Ej: La atención fue lenta, el producto no era lo esperado...',
    feedbackContact: '¿Querés que te contactemos?',
    feedbackContactPlaceholder: 'Email o teléfono (opcional)',
    redirectTitle: '¡Gracias! 🙌',
    redirectBody: 'Nos alegra que hayas tenido una buena experiencia.',
    redirectCta: '¿Nos ayudás dejando tu reseña en Google?',
    redirectButton: 'Dejar reseña en Google',
    thankYouFeedback: 'Gracias por ayudarnos a mejorar 🙏',
    thankYouFeedbackSub: 'Vamos a tener en cuenta tu comentario.',
    thankYouRedirect: '¡Gracias por tu reseña! ⭐',
    thankYouRedirectSub: 'Nos ayuda muchísimo 💛',
    closePage: 'Podés cerrar esta página.',
    sending: 'Enviando…',
    send: 'Enviar feedback',
    skip: 'Omitir',
    errRateLimit: 'Ya enviaste una reseña recientemente. Intentá más tarde.',
    errGeneric: 'Error al enviar. Intentá de nuevo.',
    errNetwork: 'Error de conexión. Intentá de nuevo.',
    errDisabled: 'Las reseñas no están habilitadas para este negocio.',
};

const REDIRECT_DELAY_S = 3;

/* ── Types ─────────────────────────────────────────────────── */

type Step = 'rating' | 'feedback' | 'redirect' | 'thankyou';
type ThankYouOrigin = 'feedback' | 'redirect';

interface Props {
    slug: string;
    config: PublicReviewConfig;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

/* ── Main component ────────────────────────────────────────── */

export function ReviewFlowClient({ slug, config }: Props) {
    const [step, setStep] = useState<Step>('rating');
    const [selectedRating, setSelectedRating] = useState(0);
    const [hoveredRating, setHoveredRating] = useState(0);
    const [comment, setComment] = useState('');
    const [contactInfo, setContactInfo] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [submitted, setSubmitted] = useState(false);
    const [error, setError] = useState('');
    const [thankYouMessage, setThankYouMessage] = useState(config.thank_you_message);
    const [redirectUrl, setRedirectUrl] = useState('');
    const [secondsLeft, setSecondsLeft] = useState(REDIRECT_DELAY_S);
    const [thankYouOrigin, setThankYouOrigin] = useState<ThankYouOrigin>('feedback');
    const redirectTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

    /* ── Auto-redirect countdown ───────────────────────────── */
    useEffect(() => {
        if (step !== 'redirect' || !redirectUrl) return;
        setSecondsLeft(REDIRECT_DELAY_S);

        redirectTimerRef.current = setInterval(() => {
            setSecondsLeft((prev) => {
                if (prev <= 1) {
                    if (redirectTimerRef.current) clearInterval(redirectTimerRef.current);
                    window.location.href = redirectUrl;
                    return 0;
                }
                return prev - 1;
            });
        }, 1000);

        return () => {
            if (redirectTimerRef.current) clearInterval(redirectTimerRef.current);
        };
    }, [step, redirectUrl]);

    /* ── Submit handler ────────────────────────────────────── */
    async function handleSubmit(rating: number, includeComment = false) {
        if (submitting || submitted) return;
        setSubmitting(true);
        setError('');

        const body: Record<string, unknown> = { rating, source: 'qr' };
        if (includeComment && comment) body.comment = comment;
        if (includeComment && contactInfo) body.contact_info = contactInfo;

        try {
            const res = await fetch(`${API_URL}/api/v1/reviews/public/${slug}/submit/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });

            if (res.status === 429) {
                setError(COPY.errRateLimit);
                setSubmitting(false);
                return;
            }

            if (!res.ok) {
                const payload = await res.json().catch(() => ({}));
                setError((payload as { detail?: string }).detail ?? COPY.errGeneric);
                setSubmitting(false);
                return;
            }

            const data = (await res.json()) as ReviewSubmitResponse;

            setSubmitted(true);
            if (data.message) setThankYouMessage(data.message);

            if (data.action === 'redirect' && data.redirect_url) {
                setRedirectUrl(data.redirect_url);
                setStep('redirect');
            } else if (data.action === 'redirect' && !data.redirect_url) {
                setThankYouOrigin('redirect');
                setStep('thankyou');
            } else {
                setThankYouOrigin('feedback');
                setStep('thankyou');
            }
        } catch {
            setError(COPY.errNetwork);
        } finally {
            setSubmitting(false);
        }
    }

    function handleRatingClick(rating: number) {
        if (submitting || submitted) return;
        setSelectedRating(rating);
        if (rating >= config.redirect_threshold) {
            handleSubmit(rating);
        } else {
            setStep('feedback');
        }
    }

    function handleRedirectClick() {
        if (redirectTimerRef.current) clearInterval(redirectTimerRef.current);
        window.location.href = redirectUrl;
    }

    /* ── Active rating label ───────────────────────────────── */
    const activeRating = hoveredRating || selectedRating;

    /* ── Star selector ─────────────────────────────────────── */
    function StarRow({ interactive }: { interactive: boolean }) {
        return (
            <div className="flex justify-center gap-3">
                {[1, 2, 3, 4, 5].map((star) => {
                    const filled = interactive
                        ? star <= (hoveredRating || selectedRating)
                        : star <= selectedRating;
                    return (
                        <button
                            key={star}
                            type="button"
                            disabled={!interactive || submitting}
                            onClick={() => interactive && handleRatingClick(star)}
                            onMouseEnter={() => interactive && setHoveredRating(star)}
                            onMouseLeave={() => interactive && setHoveredRating(0)}
                            className={`transition-all duration-200 ${
                                interactive
                                    ? 'hover:scale-125 active:scale-95 cursor-pointer'
                                    : 'cursor-default'
                            } ${filled ? 'drop-shadow-sm' : ''}`}
                            aria-label={`${star} estrella${star > 1 ? 's' : ''}`}
                        >
                            <svg
                                xmlns="http://www.w3.org/2000/svg"
                                className={`h-12 w-12 transition-colors duration-200 ${
                                    filled ? 'text-yellow-400' : 'text-slate-200'
                                }`}
                                fill={filled ? 'currentColor' : 'none'}
                                viewBox="0 0 24 24"
                                stroke="currentColor"
                                strokeWidth={filled ? 0 : 1.5}
                            >
                                <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"
                                />
                            </svg>
                        </button>
                    );
                })}
            </div>
        );
    }

    /* ── Step: Rating ─────────────────────────────────────── */
    if (step === 'rating') {
        return (
            <Shell businessName={config.business_name}>
                <FadeIn>
                    <h2 className="text-lg font-semibold text-slate-800">
                        {COPY.ratingTitle(config.business_name)}
                    </h2>
                    <p className="text-sm text-slate-500">{COPY.ratingSubtitle}</p>

                    <div className="pt-2">
                        <StarRow interactive />
                        <div className="mt-3 h-6">
                            {activeRating > 0 && (
                                <p className="text-sm font-medium text-slate-600 animate-fade-in">
                                    {RATING_LABELS[activeRating]}
                                </p>
                            )}
                        </div>
                    </div>

                    {error && <ErrorBanner message={error} />}
                    {submitting && (
                        <p className="text-xs text-slate-400 animate-pulse">{COPY.sending}</p>
                    )}
                </FadeIn>
            </Shell>
        );
    }

    /* ── Step: Feedback (low rating) ────────────────────── */
    if (step === 'feedback') {
        return (
            <Shell businessName={config.business_name}>
                <FadeIn>
                    <StarRow interactive={false} />

                    <div className="space-y-1">
                        <h2 className="text-lg font-semibold text-slate-800">{COPY.feedbackTitle}</h2>
                        <p className="text-sm text-slate-500">{COPY.feedbackSubtitle}</p>
                    </div>

                    <div className="w-full max-w-sm space-y-3 text-left">
                        <textarea
                            value={comment}
                            onChange={(e) => setComment(e.target.value)}
                            placeholder={COPY.feedbackPlaceholder}
                            rows={3}
                            maxLength={2000}
                            className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 transition-shadow"
                        />

                        {config.collect_contact && (
                            <div className="space-y-1">
                                <label className="block text-xs font-medium text-slate-500">
                                    {COPY.feedbackContact}
                                </label>
                                <input
                                    type="text"
                                    value={contactInfo}
                                    onChange={(e) => setContactInfo(e.target.value)}
                                    placeholder={COPY.feedbackContactPlaceholder}
                                    maxLength={255}
                                    className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 transition-shadow"
                                />
                            </div>
                        )}
                    </div>

                    {error && <ErrorBanner message={error} />}

                    <div className="flex gap-3">
                        <button
                            onClick={() => handleSubmit(selectedRating, true)}
                            disabled={submitting}
                            className="rounded-full bg-brand-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-500 active:bg-brand-700 transition-colors disabled:opacity-50"
                        >
                            {submitting ? COPY.sending : COPY.send}
                        </button>
                        <button
                            onClick={() => handleSubmit(selectedRating, false)}
                            disabled={submitting}
                            className="rounded-full border border-slate-200 px-6 py-2.5 text-sm font-medium text-slate-500 hover:bg-slate-50 active:bg-slate-100 transition-colors disabled:opacity-50"
                        >
                            {COPY.skip}
                        </button>
                    </div>
                </FadeIn>
            </Shell>
        );
    }

    /* ── Step: Redirect (high rating → Google) ─────────── */
    if (step === 'redirect') {
        return (
            <Shell businessName={config.business_name}>
                <FadeIn>
                    <StarRow interactive={false} />

                    <div className="space-y-1">
                        <h2 className="text-xl font-bold text-slate-900">{COPY.redirectTitle}</h2>
                        <p className="text-sm text-slate-600">{COPY.redirectBody}</p>
                        <p className="text-sm text-slate-500">{COPY.redirectCta}</p>
                    </div>

                    <button
                        onClick={handleRedirectClick}
                        className="inline-flex items-center gap-2 rounded-full bg-brand-600 px-8 py-3 text-sm font-semibold text-white shadow-md hover:bg-brand-500 active:bg-brand-700 transition-colors"
                    >
                        <GoogleIcon />
                        {COPY.redirectButton}
                    </button>

                    <div className="space-y-1">
                        <CountdownBar seconds={REDIRECT_DELAY_S} />
                        <p className="text-xs text-slate-400">
                            Redirigiendo en {secondsLeft}s…
                        </p>
                    </div>
                </FadeIn>
            </Shell>
        );
    }

    /* ── Step: Thank you ───────────────────────────────── */
    return (
        <Shell businessName={config.business_name}>
            <FadeIn>
                <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-green-50">
                    <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="h-8 w-8 text-green-500"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={2}
                    >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                </div>

                <div className="space-y-1">
                    <h2 className="text-lg font-bold text-slate-900">
                        {thankYouOrigin === 'redirect'
                            ? COPY.thankYouRedirect
                            : COPY.thankYouFeedback}
                    </h2>
                    <p className="text-sm text-slate-500">
                        {thankYouOrigin === 'redirect'
                            ? COPY.thankYouRedirectSub
                            : COPY.thankYouFeedbackSub}
                    </p>
                </div>

                <p className="text-xs text-slate-400">{COPY.closePage}</p>
            </FadeIn>
        </Shell>
    );
}

/* ── Layout shell ──────────────────────────────────────────── */

function Shell({ businessName, children }: { businessName: string; children: React.ReactNode }) {
    return (
        <div className="flex min-h-dvh items-center justify-center bg-gradient-to-b from-white via-slate-50 to-slate-100 px-4 py-12">
            <div className="w-full max-w-md space-y-8 text-center">
                {/* Business identity */}
                <div className="space-y-3">
                    <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 ring-1 ring-brand-200/40">
                        <svg
                            xmlns="http://www.w3.org/2000/svg"
                            className="h-7 w-7 text-brand-600"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth={2}
                        >
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"
                            />
                        </svg>
                    </div>
                    <h1 className="text-xl font-display font-bold text-slate-900">{businessName}</h1>
                </div>

                {/* Content card */}
                <div className="rounded-2xl bg-white/80 p-6 shadow-sm ring-1 ring-slate-900/5 backdrop-blur-sm space-y-6">
                    {children}
                </div>

                <p className="text-[10px] text-slate-300">Powered by mirubro.com</p>
            </div>
        </div>
    );
}

/* ── FadeIn wrapper ────────────────────────────────────────── */

function FadeIn({ children }: { children: React.ReactNode }) {
    return (
        <div className="animate-fade-in space-y-5">
            {children}
        </div>
    );
}

/* ── Error banner ──────────────────────────────────────────── */

function ErrorBanner({ message }: { message: string }) {
    return (
        <div className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-red-100">
            {message}
        </div>
    );
}

/* ── Countdown progress bar ────────────────────────────────── */

function CountdownBar({ seconds }: { seconds: number }) {
    return (
        <div className="mx-auto h-1 w-32 overflow-hidden rounded-full bg-slate-100">
            <div
                className="h-full rounded-full bg-brand-500"
                style={{
                    animation: `countdown-shrink ${seconds}s linear forwards`,
                }}
            />
            <style>{`
                @keyframes countdown-shrink {
                    from { width: 100%; }
                    to { width: 0%; }
                }
            `}</style>
        </div>
    );
}

/* ── Google icon (inline SVG, no external dep) ─────────────── */

function GoogleIcon() {
    return (
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none">
            <path
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
                fill="#4285F4"
            />
            <path
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                fill="#34A853"
            />
            <path
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                fill="#FBBC05"
            />
            <path
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                fill="#EA4335"
            />
        </svg>
    );
}
