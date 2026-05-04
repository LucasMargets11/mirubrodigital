'use client';

import Link from 'next/link';

import { useDismissOnboarding, useGestionOnboardingContext } from '@/features/onboarding/gestion/hooks';
import { shouldShowBanner, computeCompletionPercent, isOnboardingEnabled } from '@/features/onboarding/gestion/utils';

export function OnboardingResumeBanner() {
    const { data: ctx } = useGestionOnboardingContext({
        enabled: isOnboardingEnabled(),
    });
    const dismissMutation = useDismissOnboarding();

    if (!ctx || !shouldShowBanner(ctx)) return null;

    const percent = computeCompletionPercent(ctx.steps);
    const completedCount = ctx.steps.filter(
        (s) => s.status === 'completed' || s.status === 'skipped',
    ).length;
    const remainingCount = ctx.steps.length - completedCount;

    const handleDismiss = () => {
        dismissMutation.mutate();
    };

    return (
        <div className="flex items-center justify-between gap-4 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3">
            {/* Left */}
            <div className="flex items-center gap-3">
                {/* Rocket icon */}
                <span className="text-xl" role="img" aria-label="Cohete">
                    🚀
                </span>

                <div className="flex flex-col gap-0.5 sm:flex-row sm:items-center sm:gap-3">
                    <span className="text-sm font-medium text-blue-900">
                        Terminar de configurar tu negocio
                    </span>
                    <span className="text-xs text-blue-700">
                        {remainingCount === 1
                            ? 'Te falta 1 paso para estar listo.'
                            : `Te faltan ${remainingCount} pasos para estar listo.`}
                    </span>
                </div>

                {/* Progress bar (optional visual) */}
                <div className="hidden h-1.5 w-24 overflow-hidden rounded-full bg-blue-200 sm:block">
                    <div
                        className="h-full rounded-full bg-blue-500 transition-all"
                        style={{ width: `${percent}%` }}
                    />
                </div>
            </div>

            {/* Right */}
            <div className="flex shrink-0 items-center gap-2">
                <Link
                    href="/app/gestion/onboarding"
                    className="inline-flex items-center gap-1 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1"
                >
                    Continuar →
                </Link>

                <button
                    type="button"
                    aria-label="Descartar recordatorio de configuración"
                    onClick={handleDismiss}
                    disabled={dismissMutation.isPending}
                    className="flex h-6 w-6 items-center justify-center rounded text-blue-500 hover:bg-blue-100 hover:text-blue-700 disabled:opacity-50"
                >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>
        </div>
    );
}
