// features/onboarding/gestion/utils.ts
// Pure utility helpers for the onboarding wizard.

import type { GestionOnboardingContext, GestionOnboardingStepId, GestionOnboardingStep } from './types';
import { GESTION_ONBOARDING_STEP_ORDER } from './constants';

/** Return the step the wizard should open on load. */
export function resolveInitialStep(ctx: GestionOnboardingContext): GestionOnboardingStepId {
    const currentStep = ctx.progress.current_step as GestionOnboardingStepId | '';
    if (currentStep && GESTION_ONBOARDING_STEP_ORDER.includes(currentStep)) {
        return currentStep;
    }
    return 'business_basics';
}

/** Return the next step after the given one, or null if there is none. */
export function nextStep(stepId: GestionOnboardingStepId): GestionOnboardingStepId | null {
    const idx = GESTION_ONBOARDING_STEP_ORDER.indexOf(stepId);
    const next = GESTION_ONBOARDING_STEP_ORDER[idx + 1];
    return next ?? null;
}

/** Find a step descriptor by ID. */
export function findStep(steps: GestionOnboardingStep[], id: GestionOnboardingStepId): GestionOnboardingStep | undefined {
    return steps.find((s) => s.id === id);
}

/** Returns true when the wizard should auto-complete (has both products and sales). */
export function shouldAutoComplete(ctx: GestionOnboardingContext): boolean {
    return ctx.catalog.products_count > 0 && ctx.sales.sales_count > 0;
}

/** Returns true when first_product step should be auto-skipped on load. */
export function shouldAutoSkipFirstProduct(ctx: GestionOnboardingContext): boolean {
    return (
        ctx.catalog.products_count > 0 &&
        !ctx.progress.skipped_steps.includes('first_product')
    );
}

/** Returns true if the rollout flag is enabled (read from env). */
export function isOnboardingEnabled(): boolean {
    return process.env.NEXT_PUBLIC_NEW_ONBOARDING_ENABLED === 'true';
}

/** Returns true if the banner should be shown for this context. */
export function shouldShowBanner(ctx: GestionOnboardingContext): boolean {
    if (!isOnboardingEnabled()) return false;
    if (!['owner', 'admin'].includes(ctx.user_role)) return false;
    if (ctx.progress.completed_at !== null) return false;
    if (ctx.progress.dismissed_at !== null) return false;
    if (!['onboarding', 'trialing', 'active'].includes(ctx.business.status)) return false;
    return true;
}

/** Return the overall completion percentage (0–100). */
export function computeCompletionPercent(steps: GestionOnboardingStep[]): number {
    const done = steps.filter((s) => s.status === 'completed' || s.status === 'skipped').length;
    return Math.round((done / steps.length) * 100);
}
