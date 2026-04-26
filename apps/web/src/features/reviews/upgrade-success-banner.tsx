'use client';

/**
 * UpgradeSuccessBanner — shown once after returning from MercadoPago checkout.
 *
 * Renders three states:
 *  1. «activating» — webhook hasn't fired yet, polling config every 2s
 *  2. «success»   — plan is now Pro, shows confirmation + feature list
 *  3. «timeout»   — polling exhausted without Pro, shows a soft message
 *
 * Auto-cleans ?upgrade= from the URL on dismiss.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { getReviewSettings } from '@/features/reviews/api';
import type { ReviewConfig } from '@/features/reviews/types';

const POLL_INTERVAL_MS = 2_000;
const POLL_MAX_ATTEMPTS = 8; // 16 seconds max

type BannerState = 'activating' | 'success' | 'timeout';

type Props = {
    /** Initial config already fetched by the dashboard. */
    initialConfig: ReviewConfig | null;
    /** Fired when polling detects Pro so parent can refresh its state. */
    onUpgradeConfirmed?: (config: ReviewConfig) => void;
};

export function UpgradeSuccessBanner({ initialConfig, onUpgradeConfirmed }: Props) {
    const router = useRouter();
    const [state, setState] = useState<BannerState>(() =>
        initialConfig?.smart_filter_allowed ? 'success' : 'activating',
    );
    const [dismissed, setDismissed] = useState(false);
    const pollCount = useRef(0);

    // ── Polling ────────────────────────────────────────────
    const poll = useCallback(async () => {
        try {
            const cfg = await getReviewSettings();
            if (cfg?.smart_filter_allowed) {
                setState('success');
                onUpgradeConfirmed?.(cfg);
                // Notify nav + other components
                window.dispatchEvent(new Event('reviews-config-changed'));
                return true; // stop
            }
        } catch { /* ignore */ }
        return false;
    }, [onUpgradeConfirmed]);

    useEffect(() => {
        if (state !== 'activating') return;

        const id = setInterval(async () => {
            pollCount.current += 1;
            const done = await poll();
            if (done || pollCount.current >= POLL_MAX_ATTEMPTS) {
                clearInterval(id);
                if (!done) setState('timeout');
            }
        }, POLL_INTERVAL_MS);

        return () => clearInterval(id);
    }, [state, poll]);

    // ── Dismiss handler ────────────────────────────────────
    function handleDismiss() {
        setDismissed(true);
        // Clean upgrade param from URL without full navigation
        const url = new URL(window.location.href);
        url.searchParams.delete('upgrade');
        url.searchParams.delete('change_id');
        router.replace((url.pathname + (url.search || '')) as any, { scroll: false });
    }

    if (dismissed) return null;

    // ── Activating ─────────────────────────────────────────
    if (state === 'activating') {
        return (
            <div className="flex items-center gap-3 rounded-xl border border-brand-200 bg-brand-50 px-4 py-3 animate-pulse">
                <span className="shrink-0 text-brand-500">
                    <SpinnerIcon />
                </span>
                <div className="flex-1">
                    <p className="text-sm font-semibold text-brand-800">
                        Procesando tu upgrade…
                    </p>
                    <p className="text-xs text-brand-600">
                        Estamos confirmando el pago. Esto puede tardar unos segundos.
                    </p>
                </div>
            </div>
        );
    }

    // ── Timeout ────────────────────────────────────────────
    if (state === 'timeout') {
        return (
            <div className="relative flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
                <span className="mt-0.5 shrink-0 text-amber-500">
                    <ClockIcon />
                </span>
                <div className="flex-1">
                    <p className="text-sm font-semibold text-amber-800">
                        Tu pago se está procesando
                    </p>
                    <p className="text-xs text-amber-700">
                        El pago fue registrado pero la activación puede demorar unos minutos.
                        Refrescá la página en un momento para ver tu plan Pro activo.
                    </p>
                </div>
                <button
                    onClick={handleDismiss}
                    className="shrink-0 rounded-lg p-1 text-amber-400 hover:bg-amber-100 hover:text-amber-600 transition-colors"
                    aria-label="Cerrar"
                >
                    <XIcon />
                </button>
            </div>
        );
    }

    // ── Success ────────────────────────────────────────────
    return (
        <div className="relative rounded-xl border border-green-200 bg-gradient-to-r from-green-50 to-emerald-50 px-5 py-4 shadow-sm">
            <button
                onClick={handleDismiss}
                className="absolute right-3 top-3 rounded-lg p-1 text-green-400 hover:bg-green-100 hover:text-green-600 transition-colors"
                aria-label="Cerrar"
            >
                <XIcon />
            </button>

            <div className="flex items-start gap-3">
                <span className="mt-0.5 shrink-0 flex h-8 w-8 items-center justify-center rounded-full bg-green-100 text-green-600">
                    <CheckIcon />
                </span>
                <div className="space-y-2">
                    <div>
                        <p className="text-sm font-bold text-green-900">
                            ¡Upgrade exitoso! Ya tenés Reseñas Pro
                        </p>
                        <p className="text-xs text-green-700">
                            Tu plan se actualizó correctamente. Estas funcionalidades ya están activas:
                        </p>
                    </div>
                    <ul className="grid gap-1 text-xs text-green-800">
                        <li className="flex items-center gap-2">
                            <CheckBullet /> Filtro inteligente activado
                        </li>
                        <li className="flex items-center gap-2">
                            <CheckBullet /> Feedback privado operativo
                        </li>
                        <li className="flex items-center gap-2">
                            <CheckBullet /> Analytics avanzados disponibles
                        </li>
                    </ul>
                </div>
            </div>
        </div>
    );
}

/* ── Tiny icons ─────────────────────────────────────────── */

function SpinnerIcon() {
    return (
        <svg className="h-5 w-5 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
    );
}

function ClockIcon() {
    return (
        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
    );
}

function CheckIcon() {
    return (
        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
    );
}

function CheckBullet() {
    return (
        <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5 shrink-0 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
    );
}

function XIcon() {
    return (
        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
    );
}
