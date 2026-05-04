'use client';

import { useRouter } from 'next/navigation';
import { useCallback, useState } from 'react';

import { Card, CardContent } from '@/components/ui/card';
import { useGestionOnboardingContext } from '@/features/onboarding/gestion/hooks';
import { isOnboardingEnabled, shouldShowBanner } from '@/features/onboarding/gestion/utils';

import { useGestionSetupContext } from '../hooks';
import { getRecommendedSetupTask } from '../utils';

interface GestionSetupProgressBannerProps {
    onOpenHelp: () => void;
}

const ALLOWED_ROLES = ['owner', 'admin', 'manager'] as const;
type AllowedRole = (typeof ALLOWED_ROLES)[number];

function getDismissKey(businessId: number): string {
    return `setup-banner-dismissed-${businessId}`;
}

export function GestionSetupProgressBanner({ onOpenHelp }: GestionSetupProgressBannerProps) {
    const setupQuery = useGestionSetupContext();
    const onboardingQuery = useGestionOnboardingContext({
        enabled: isOnboardingEnabled(),
    });

    const router = useRouter();
    const [dismissedLocal, setDismissedLocal] = useState(false);

    const setupCtx = setupQuery.data;
    const onboardingCtx = onboardingQuery.data;

    // ── Dismiss logic ────────────────────────────────────────────────────────
    const businessId = onboardingCtx?.business?.id;

    const isDismissedInSession = useCallback((): boolean => {
        if (typeof window === 'undefined' || businessId === undefined) return false;
        return sessionStorage.getItem(getDismissKey(businessId)) === '1';
    }, [businessId]);

    const handleDismiss = useCallback(() => {
        if (businessId !== undefined && typeof window !== 'undefined') {
            sessionStorage.setItem(getDismissKey(businessId), '1');
        }
        setDismissedLocal(true);
    }, [businessId]);

    // ── Visibility rules ─────────────────────────────────────────────────────

    // 1. Onboarding still active → OnboardingResumeBanner has priority
    if (onboardingCtx && shouldShowBanner(onboardingCtx)) return null;

    // 2. Setup data not yet loaded or failed
    if (!setupCtx) return null;

    // 3. No steps available for this plan
    if (setupCtx.progress.total === 0) return null;

    // 4. All steps completed
    if (setupCtx.progress.completed >= setupCtx.progress.total) return null;

    // 5. Role check — only configurators see this banner
    if (
        onboardingCtx &&
        !(ALLOWED_ROLES as readonly string[]).includes(onboardingCtx.user_role)
    ) return null;

    // 6. Dismissed this session
    if (dismissedLocal || isDismissedInSession()) return null;

    // ── Data ─────────────────────────────────────────────────────────────────
    const { completed, total } = setupCtx.progress;
    const percent = Math.round((completed / total) * 100);
    const recommendedTask = getRecommendedSetupTask(setupCtx);

    return (
        <Card className="border-slate-200 bg-slate-50 shadow-none">
            <CardContent className="px-4 py-3">
                <div className="flex items-center justify-between gap-4">
                    {/* Left: icon + text + progress */}
                    <div className="flex min-w-0 flex-1 items-start gap-3">
                        {/* Icon */}
                        <span className="mt-0.5 flex-shrink-0 text-lg" role="img" aria-label="Configuración">
                            ⚙️
                        </span>

                        <div className="min-w-0 flex-1 space-y-1.5">
                            {/* Title + counter */}
                            <div className="flex flex-wrap items-baseline gap-2">
                                <span className="text-sm font-semibold text-slate-900">
                                    Configuración del negocio
                                </span>
                                <span className="text-xs text-slate-500">
                                    {completed} de {total} pasos completados
                                </span>
                            </div>

                            {/* Progress bar */}
                            <div className="h-1.5 w-full max-w-xs overflow-hidden rounded-full bg-slate-200">
                                <div
                                    className="h-full rounded-full bg-brand-500 transition-all duration-300"
                                    style={{ width: `${percent}%` }}
                                    role="progressbar"
                                    aria-valuenow={percent}
                                    aria-valuemin={0}
                                    aria-valuemax={100}
                                />
                            </div>

                            {/* Next recommended task */}
                            {recommendedTask && (
                                <p className="text-xs text-slate-500">
                                    Siguiente:{' '}
                                    <span className="font-medium text-slate-700">
                                        {recommendedTask.title}
                                    </span>
                                </p>
                            )}
                        </div>
                    </div>

                    {/* Right: CTAs + close */}
                    <div className="flex shrink-0 items-center gap-2">
                        {/* CTA primary — go directly to recommended task */}
                        {recommendedTask ? (
                            <button
                                type="button"
                                onClick={() => router.push(recommendedTask.cta.href as never)}
                                className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-1"
                            >
                                {recommendedTask.cta.label} →
                            </button>
                        ) : (
                            /* Fallback when no pending task but somehow total > completed */
                            <button
                                type="button"
                                onClick={onOpenHelp}
                                className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-1"
                            >
                                Continuar →
                            </button>
                        )}

                        {/* CTA secondary — open HelpModal in setup tab */}
                        <button
                            type="button"
                            onClick={onOpenHelp}
                            className="hidden rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:border-slate-400 hover:text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-1 sm:inline-flex sm:items-center"
                        >
                            Ver todos los pasos
                        </button>

                        {/* Dismiss button */}
                        <button
                            type="button"
                            aria-label="Cerrar banner de configuración"
                            onClick={handleDismiss}
                            className="flex h-6 w-6 items-center justify-center rounded text-slate-400 transition hover:bg-slate-200 hover:text-slate-600"
                        >
                            <svg
                                className="h-3.5 w-3.5"
                                fill="none"
                                viewBox="0 0 24 24"
                                stroke="currentColor"
                                strokeWidth={2}
                            >
                                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
