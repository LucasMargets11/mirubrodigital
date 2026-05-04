// features/onboarding/gestion/constants.ts
// Single source of truth for step ordering, labels and copy.

import type { GestionOnboardingStepId } from './types';

export const GESTION_ONBOARDING_STEP_ORDER: GestionOnboardingStepId[] = [
    'business_basics',
    'first_product',
    'sales_setup',
];

export const STEP_LABELS: Record<GestionOnboardingStepId, string> = {
    business_basics: 'Datos del negocio',
    first_product: 'Primer producto',
    sales_setup: 'Preparar ventas',
};

/** Steps that show a "Saltar este paso" button. Must match backend SKIPPABLE_STEPS. */
export const SKIPPABLE_STEPS: Set<GestionOnboardingStepId> = new Set([
    'business_basics',
    'first_product',
]);

/** Business names that are treated as unset (placeholder values). */
export const NAME_PLACEHOLDERS = new Set([
    'mi negocio',
    'my business',
    'negocio',
]);
