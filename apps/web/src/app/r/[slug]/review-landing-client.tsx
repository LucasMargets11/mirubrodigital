'use client';

import { useEffect, useState } from 'react';

interface Props {
    businessName: string;
    reviewUrl: string;
}

/**
 * Public landing page for QR de Reseñas.
 * Decision 3: Shows business name + CTA, then auto-redirects after ~3s.
 * Prepared for future tracking (visit counting, UTM params, etc.).
 */
export function ReviewLandingClient({ businessName, reviewUrl }: Props) {
    const [countdown, setCountdown] = useState(3);

    useEffect(() => {
        // Future: track visit here (analytics event, API call, etc.)

        const timer = setInterval(() => {
            setCountdown((prev) => {
                if (prev <= 1) {
                    clearInterval(timer);
                    window.location.href = reviewUrl;
                    return 0;
                }
                return prev - 1;
            });
        }, 1000);

        return () => clearInterval(timer);
    }, [reviewUrl]);

    return (
        <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100 px-4">
            <div className="w-full max-w-md text-center space-y-6">
                <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-100">
                    <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="h-8 w-8 text-brand-600"
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

                <div>
                    <h1 className="text-2xl font-bold text-slate-900">{businessName}</h1>
                    <p className="mt-2 text-slate-600">
                        ¡Gracias por visitarnos! Contanos tu experiencia.
                    </p>
                </div>

                <a
                    href={reviewUrl}
                    className="inline-block rounded-full bg-brand-600 px-8 py-3 text-sm font-semibold text-white shadow-md hover:bg-brand-700 transition-colors"
                >
                    Dejar una reseña en Google
                </a>

                <p className="text-xs text-slate-400">
                    Redirigiendo automáticamente en {countdown}s…
                </p>
            </div>
        </div>
    );
}
