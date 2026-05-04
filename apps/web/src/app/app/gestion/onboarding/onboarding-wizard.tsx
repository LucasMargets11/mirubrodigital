'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';

import { useGestionOnboardingContext, useCompleteOnboarding } from '@/features/onboarding/gestion/hooks';
import { resolveInitialStep, shouldAutoComplete, shouldAutoSkipFirstProduct, isOnboardingEnabled } from '@/features/onboarding/gestion/utils';
import { GESTION_ONBOARDING_STEP_ORDER, STEP_LABELS } from '@/features/onboarding/gestion/constants';
import type { GestionOnboardingStepId } from '@/features/onboarding/gestion/types';

import { BusinessBasicsStep } from './steps/business-basics-step';
import { FirstProductStep } from './steps/first-product-step';
import { SalesSetupStep } from './steps/sales-setup-step';
import { CompletionScreen } from './steps/completion-screen';

// ─── Stepper indicator ────────────────────────────────────────────────────────

function StepIndicator({
    steps,
    currentStep,
}: {
    steps: { id: GestionOnboardingStepId; status: string }[];
    currentStep: GestionOnboardingStepId;
}) {
    return (
        <div className="flex items-center gap-2">
            {steps.map((step, idx) => {
                const isDone = step.status === 'completed' || step.status === 'skipped';
                const isActive = step.id === currentStep;
                return (
                    <div key={step.id} className="flex items-center gap-2">
                        <div
                            className={[
                                'flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold',
                                isDone
                                    ? 'bg-emerald-500 text-white'
                                    : isActive
                                      ? 'bg-blue-600 text-white'
                                      : 'bg-slate-200 text-slate-500',
                            ].join(' ')}
                        >
                            {isDone ? (
                                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                                </svg>
                            ) : (
                                idx + 1
                            )}
                        </div>
                        <span
                            className={[
                                'text-xs font-medium',
                                isActive ? 'text-slate-900' : 'text-slate-400',
                            ].join(' ')}
                        >
                            {STEP_LABELS[step.id]}
                        </span>
                        {idx < steps.length - 1 && (
                            <div className="h-px w-6 bg-slate-200" />
                        )}
                    </div>
                );
            })}
        </div>
    );
}

// ─── Main wizard ──────────────────────────────────────────────────────────────

export default function OnboardingWizard() {
    const router = useRouter();
    const { data: ctx, isLoading, isError } = useGestionOnboardingContext();
    const completeOnboarding = useCompleteOnboarding();
    const [activeStep, setActiveStep] = useState<GestionOnboardingStepId>('business_basics');
    const [showCompletion, setShowCompletion] = useState(false);
    const [autoCompleteError, setAutoCompleteError] = useState(false);
    const [completeError, setCompleteError] = useState(false);
    // Prevents the step-resolution effect from re-running after context is updated
    // by mutations (e.g. sales_setup updating progress.current_step to '').
    const hasInitializedRef = useRef(false);

    // Redirect if rollout is off
    useEffect(() => {
        if (!isOnboardingEnabled()) {
            router.replace('/app/gestion/dashboard');
        }
    }, [router]);

    // Once context loads, set the initial step or auto-complete
    useEffect(() => {
        if (!ctx) return;

        // Already completed
        if (ctx.progress.completed_at) {
            setShowCompletion(true);
            return;
        }

        // Auto-complete: has both products AND sales
        if (shouldAutoComplete(ctx)) {
            completeOnboarding.mutate(undefined, {
                onSuccess: () => setShowCompletion(true),
                onError: () => setAutoCompleteError(true),
            });
            return;
        }

        // Guard: only resolve the initial step once. Subsequent context updates
        // (e.g. from setQueryData after mutations) must NOT reset the active step.
        if (hasInitializedRef.current) return;
        hasInitializedRef.current = true;

        // Set initial step
        const initial = resolveInitialStep(ctx);
        // If products exist, skip first_product and go to sales_setup
        if (initial === 'first_product' && shouldAutoSkipFirstProduct(ctx)) {
            setActiveStep('sales_setup');
        } else if (
            initial === 'business_basics' &&
            shouldAutoSkipFirstProduct(ctx) &&
            ctx.steps.find((s) => s.id === 'business_basics')?.status === 'completed'
        ) {
            // ISSUE-M1: business_basics already done and products exist — skip straight to sales_setup
            setActiveStep('sales_setup');
        } else {
            setActiveStep(initial);
        }
    }, [ctx]); // eslint-disable-line react-hooks/exhaustive-deps

    const goToStep = useCallback((step: GestionOnboardingStepId) => {
        setActiveStep(step);
    }, []);

    const handleStepComplete = useCallback((nextStep: GestionOnboardingStepId | null) => {
        if (nextStep) {
            setActiveStep(nextStep);
        } else {
            setShowCompletion(true);
        }
    }, []);

    if (!isOnboardingEnabled()) return null;

    if (isLoading) {
        return (
            <div className="flex min-h-[400px] items-center justify-center">
                <div className="text-sm text-slate-500">Cargando asistente de configuración...</div>
            </div>
        );
    }

    if (isError || !ctx) {
        return (
            <div className="rounded-lg bg-red-50 p-6 text-center">
                <p className="text-sm text-red-800">No se pudo cargar el asistente. Recargá la página.</p>
            </div>
        );
    }

    if (completeError) {
        return (
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="rounded-lg border border-red-200 bg-red-50 p-4">
                    <p className="text-sm text-red-800">
                        No pudimos finalizar la configuración. Intentá de nuevo.
                    </p>
                </div>
                <div className="mt-4 text-center">
                    <button
                        type="button"
                        onClick={() => {
                            setCompleteError(false);
                            completeOnboarding.mutate(undefined, {
                                onSuccess: () => setShowCompletion(true),
                                onError: () => setCompleteError(true),
                            });
                        }}
                        disabled={completeOnboarding.isPending}
                        className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                    >
                        {completeOnboarding.isPending ? 'Finalizando...' : 'Reintentar'}
                    </button>
                </div>
            </div>
        );
    }

    if (autoCompleteError) {
        return (
            <div className="rounded-lg bg-red-50 p-6 text-center">
                <p className="text-sm text-red-800">No se pudo finalizar la configuración automáticamente. Recargá la página.</p>
            </div>
        );
    }

    if (showCompletion) {
        return <CompletionScreen hasProducts={(ctx?.catalog.products_count ?? 0) > 0} />;
    }

    const stepDescriptors = ctx.steps.map((s) => ({
        id: s.id as GestionOnboardingStepId,
        status: s.status,
    }));

    return (
        <div className="mx-auto max-w-2xl space-y-8 py-6">
            {/* Header */}
            <div className="space-y-2">
                <h1 className="text-2xl font-bold text-slate-900">
                    ¡Empecemos! Configurá tu negocio en 3 pasos
                </h1>
                <p className="text-sm text-slate-500">
                    Tomamos los datos más importantes para que puedas vender desde hoy. Después podés completar el resto cuando quieras.
                </p>
            </div>

            {/* Stepper */}
            <StepIndicator steps={stepDescriptors} currentStep={activeStep} />

            {/* Active step */}
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                {activeStep === 'business_basics' && (
                    <BusinessBasicsStep
                        context={ctx}
                        onComplete={() => handleStepComplete(shouldAutoSkipFirstProduct(ctx) ? 'sales_setup' : 'first_product')}
                        onSkip={() => goToStep(shouldAutoSkipFirstProduct(ctx) ? 'sales_setup' : 'first_product')}
                    />
                )}
                {activeStep === 'first_product' && (
                    <FirstProductStep
                        context={ctx}
                        onComplete={() => handleStepComplete('sales_setup')}
                        onSkip={() => {
                            goToStep('sales_setup');
                        }}
                        onBack={() => goToStep('business_basics')}
                    />
                )}
                {activeStep === 'sales_setup' && (
                    <SalesSetupStep
                        context={ctx}
                        onComplete={() => {
                            if (!completeOnboarding.isPending) {
                                completeOnboarding.mutate(undefined, {
                                    onSuccess: () => setShowCompletion(true),
                                    onError: () => setCompleteError(true),
                                });
                            }
                        }}
                        isCompleting={completeOnboarding.isPending}
                        onBack={() => goToStep('first_product')}
                    />
                )}
            </div>

            {/* Quick-exit */}
            <div className="text-center">
                <button
                    type="button"
                    className="text-xs text-slate-400 hover:text-slate-600 hover:underline"
                    onClick={() => router.push('/app/gestion/dashboard')}
                >
                    Ya configuré todo, ir al inicio
                </button>
            </div>
        </div>
    );
}
