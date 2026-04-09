import { useMemo } from 'react';

import type {
    GestionPlan,
    HowToItem,
    SetupSection,
    SetupStep,
    StepStatusMap,
    TipItem,
    UpgradeNudge,
} from './types';
import {
    GESTION_HOWTO_ITEMS,
    GESTION_SECTIONS,
    GESTION_SETUP_STEPS,
    GESTION_TIPS,
    GESTION_UPGRADE_NUDGES,
} from './data/gestion-comercial';
import { PLAN_TIER } from './types';

// ─── Filtering helpers ────────────────────────────────────────────────

function planAllows(itemMinPlan: GestionPlan, currentPlan: GestionPlan): boolean {
    return (PLAN_TIER[itemMinPlan] ?? 0) <= (PLAN_TIER[currentPlan] ?? 0);
}

export function getVisibleSteps(steps: SetupStep[], plan: GestionPlan): SetupStep[] {
    return steps.filter((s) => planAllows(s.minPlan, plan));
}

export function getVisibleSections(
    sections: SetupSection[],
    plan: GestionPlan,
): SetupSection[] {
    return sections.filter((s) => planAllows(s.minPlan, plan));
}

export function getVisibleHowTo(items: HowToItem[], plan: GestionPlan): HowToItem[] {
    return items.filter((i) => planAllows(i.minPlan, plan));
}

export function getVisibleTips(items: TipItem[], plan: GestionPlan): TipItem[] {
    return items.filter((i) => planAllows(i.minPlan, plan));
}

export function getUpgradeNudge(plan: GestionPlan): UpgradeNudge | null {
    return GESTION_UPGRADE_NUDGES[plan] ?? null;
}

// ─── Progress helpers ─────────────────────────────────────────────────

export function computeProgress(
    steps: SetupStep[],
    statusMap: StepStatusMap,
): { completed: number; total: number } {
    let completed = 0;
    for (const step of steps) {
        if (statusMap[step.id] === 'completed') completed++;
    }
    return { completed, total: steps.length };
}

// ─── React hook ───────────────────────────────────────────────────────

/**
 * Returns the full Gestión Comercial help content filtered for `plan`.
 *
 * `statusMap` is optional — pass it once the backend endpoint is wired.
 * Until then, components can default to an empty object and every step
 * renders as pending.
 */
export function useGestionHelp(plan: GestionPlan | null, statusMap: StepStatusMap = {}) {
    return useMemo(() => {
        // If plan hasn't resolved yet, return empty lists so the modal
        // can show a loading state instead of incorrectly defaulting to START.
        if (!plan) {
            return {
                steps: [] as SetupStep[],
                sections: [] as SetupSection[],
                howto: [] as HowToItem[],
                tips: [] as TipItem[],
                nudge: null as UpgradeNudge | null,
                progress: { completed: 0, total: 0 },
                statusMap,
                resolved: false,
            };
        }

        const steps = getVisibleSteps(GESTION_SETUP_STEPS, plan);
        const sections = getVisibleSections(GESTION_SECTIONS, plan);
        const howto = getVisibleHowTo(GESTION_HOWTO_ITEMS, plan);
        const tips = getVisibleTips(GESTION_TIPS, plan);
        const nudge = getUpgradeNudge(plan);
        const progress = computeProgress(steps, statusMap);

        return { steps, sections, howto, tips, nudge, progress, statusMap, resolved: true };
    }, [plan, statusMap]);
}
