import { GESTION_SETUP_STEPS } from '@/features/help/data/gestion-comercial';
import type { StepStatusMap } from '@/features/help/types';

import { SETUP_PRIORITY_ORDER } from './constants';
import type { GestionSetupContext } from './types';

/**
 * Transforms the backend `status_map` from `GestionSetupContext` into the
 * `StepStatusMap` shape expected by `HelpModal` / `useGestionHelp`.
 *
 * The backend already returns keys with the `gestion.` prefix and values
 * collapsed to `'completed' | 'pending'`, so this is a direct pass-through.
 */
export function transformSetupContextToStatusMap(
    ctx: GestionSetupContext,
): StepStatusMap {
    return { ...ctx.status_map };
}

/**
 * Returns the next recommended setup step for the user to complete.
 *
 * Steps are evaluated in priority order for the business's plan.
 * Only steps with status 'pending' are returned — 'completed', 'upgrade',
 * and 'upgrade_addon' are all skipped.
 *
 * Returns null when all steps are done or no matching step definition exists.
 */
export function getRecommendedSetupTask(
    ctx: GestionSetupContext,
): { id: string; title: string; description: string; cta: { label: string; href: string } } | null {
    const planCode = ctx.plan.code; // 'starter' | 'pro' | 'business' | 'enterprise'
    const priorityOrder = SETUP_PRIORITY_ORDER[planCode] ?? SETUP_PRIORITY_ORDER['starter'];

    for (const stepId of priorityOrder) {
        const task = ctx.tasks[stepId];
        if (!task || task.status !== 'pending') continue;

        const stepDef = GESTION_SETUP_STEPS.find((s) => s.id === stepId);
        if (!stepDef) continue;

        return {
            id: stepId,
            title: stepDef.title,
            description: stepDef.description,
            cta: stepDef.cta,
        };
    }

    return null;
}
