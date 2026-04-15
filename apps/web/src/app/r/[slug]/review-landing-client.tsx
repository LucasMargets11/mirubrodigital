'use client';

import { useEffect, useState } from 'react';
import type { PublicReviewConfig } from '@/features/reviews/types';

interface Props {
    config: PublicReviewConfig;
}

/**
 * Public landing page for QR de Reseñas — direct mode.
 *
 * In `direct` mode all visitors are sent straight to Google Reviews.
 * No rating is collected, no Review objects are created.
 * Tracking (visit count) is already handled server-side by the API
 * when the public config is fetched.
 *
 * Pro businesses get their logo and accent color applied.
 */
export function ReviewLandingClient({ config }: Props) {
    const { business_name, redirect_url, thank_you_message, logo_url, accent_color, is_pro } = config;
    const [countdown, setCountdown] = useState(3);

    const hasRedirect = Boolean(redirect_url);

    useEffect(() => {
        if (!hasRedirect) return;

        const timer = setInterval(() => {
            setCountdown((prev) => {
                if (prev <= 1) {
                    clearInterval(timer);
                    window.location.href = redirect_url;
                    return 0;
                }
                return prev - 1;
            });
        }, 1000);

        return () => clearInterval(timer);
    }, [redirect_url, hasRedirect]);

    /* Accent-derived CSS custom properties for Pro */
    const accentStyle = accent_color
        ? { '--accent': accent_color, '--accent-light': `${accent_color}1a` } as React.CSSProperties
        : undefined;

    const btnClass = accent_color
        ? 'inline-block rounded-full px-8 py-3 text-sm font-semibold text-white shadow-md transition-colors'
        : 'inline-block rounded-full bg-brand-600 px-8 py-3 text-sm font-semibold text-white shadow-md hover:bg-brand-700 transition-colors';

    const btnStyle = accent_color
        ? { backgroundColor: accent_color }
        : undefined;

    return (
        <div className="flex min-h-dvh items-center justify-center bg-gradient-to-b from-white via-slate-50 to-slate-100 px-4 py-12">
            <div className="w-full max-w-md text-center space-y-6">
                {/* Business identity */}
                <div className="space-y-3" style={accentStyle}>
                    {logo_url ? (
                        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-white shadow-sm ring-1 ring-slate-200/60 overflow-hidden">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                                src={logo_url}
                                alt={business_name}
                                className="h-12 w-12 object-contain"
                            />
                        </div>
                    ) : (
                        <div
                            className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-100"
                            style={accent_color ? { backgroundColor: `${accent_color}1a` } : undefined}
                        >
                            <StarIcon color={accent_color} />
                        </div>
                    )}

                    <div>
                        <h1 className="text-2xl font-bold text-slate-900">{business_name}</h1>
                        <p className="mt-2 text-slate-600">
                            {thank_you_message || '¡Gracias por visitarnos! Contanos tu experiencia.'}
                        </p>
                    </div>
                </div>

                {/* Card */}
                <div className="rounded-2xl bg-white/80 p-6 shadow-sm ring-1 ring-slate-900/5 backdrop-blur-sm space-y-5">
                    {hasRedirect ? (
                        <>
                            <p className="text-sm text-slate-500">
                                Tu opinión nos ayuda a mejorar
                            </p>

                            <a
                                href={redirect_url}
                                className={btnClass}
                                style={btnStyle}
                            >
                                <span className="inline-flex items-center gap-2">
                                    <GoogleIcon />
                                    Dejar una reseña en Google
                                </span>
                            </a>

                            <div className="space-y-1">
                                <CountdownBar seconds={3} accentColor={accent_color} />
                                <p className="text-xs text-slate-400">
                                    Redirigiendo en {countdown}s…
                                </p>
                            </div>
                        </>
                    ) : (
                        <p className="text-sm text-slate-500">
                            El negocio aún no configuró su enlace de reseñas.
                        </p>
                    )}
                </div>

                <p className="text-[10px] text-slate-300">
                    {is_pro ? `Reseñas de ${business_name}` : 'Powered by mirubro.com'}
                </p>
            </div>
        </div>
    );
}

/* ── Star icon ─────────────────────────────────────────────── */

function StarIcon({ color }: { color?: string | null }) {
    return (
        <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-8 w-8"
            style={{ color: color || undefined }}
            fill="none"
            viewBox="0 0 24 24"
            stroke={color || 'currentColor'}
            strokeWidth={2}
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"
            />
        </svg>
    );
}

/* ── Google icon ───────────────────────────────────────────── */

function GoogleIcon() {
    return (
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none">
            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
        </svg>
    );
}

/* ── Countdown progress bar ────────────────────────────────── */

function CountdownBar({ seconds, accentColor }: { seconds: number; accentColor?: string | null }) {
    return (
        <div className="mx-auto h-1 w-32 overflow-hidden rounded-full bg-slate-100">
            <div
                className={accentColor ? 'h-full rounded-full' : 'h-full rounded-full bg-brand-500'}
                style={{
                    animation: `countdown-shrink ${seconds}s linear forwards`,
                    ...(accentColor ? { backgroundColor: accentColor } : {}),
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
