// ─── Plan types ───────────────────────────────────────────────────────
// Canonical plan codes used internally by the help feature.
// The API may return 'starter' (DB value) or 'start' (legacy);
// always normalise with `normalizeGestionPlan` before use.

export type GestionPlan = 'start' | 'pro' | 'business' | 'enterprise';

export const PLAN_TIER: Record<GestionPlan, number> = {
    start: 0,
    pro: 1,
    business: 2,
    enterprise: 3,
};

// Map of known API values → canonical GestionPlan
const PLAN_ALIASES: Record<string, GestionPlan> = {
    start: 'start',
    starter: 'start',
    pro: 'pro',
    business: 'business',
    enterprise: 'enterprise',
};

/**
 * Normalise any plan value coming from the API into a canonical GestionPlan.
 * Accepts a raw string (e.g. 'starter', 'PRO') or the plan object returned by
 * useEntitlements().plan ({ plan: 'pro', status: 'active', … }).
 *
 * Returns `null` when the value cannot be resolved — callers should treat null
 * as "still loading / unknown" and NOT fall back to 'start'.
 */
export function normalizeGestionPlan(
    raw: unknown,
): GestionPlan | null {
    if (raw == null) return null;

    // useEntitlements().plan is an object with a .plan string property
    const str: string | undefined =
        typeof raw === 'string'
            ? raw
            : typeof raw === 'object' && 'plan' in (raw as Record<string, unknown>)
              ? String((raw as Record<string, unknown>).plan)
              : undefined;

    if (!str) {
        if (process.env.NODE_ENV !== 'production') {
            console.warn('[help] normalizeGestionPlan: unexpected value', raw);
        }
        return null;
    }

    const key = str.toLowerCase().trim();
    const result = PLAN_ALIASES[key];

    if (!result && process.env.NODE_ENV !== 'production') {
        console.warn(`[help] normalizeGestionPlan: unknown plan code "${str}"`);
    }

    return result ?? null;
}

// ─── Tabs ─────────────────────────────────────────────────────────────

export type HelpTabId = 'setup' | 'howto' | 'tips';

// ─── Setup step model ─────────────────────────────────────────────────

export type StepObligation = 'required' | 'recommended' | 'optional';

export type StepStatus = 'pending' | 'completed';

/** Map of step id → completion status. Provided externally (mock or API). */
export type StepStatusMap = Record<string, StepStatus>;

export interface SetupStepCta {
    label: string;
    href: string;
}

export interface SetupStep {
    id: string;
    title: string;
    description: string;
    section: string;
    minPlan: GestionPlan;
    obligation: StepObligation;
    cta: SetupStepCta;
    /** Optional secondary CTA (e.g., products dual CTA). */
    ctaSecondary?: SetupStepCta;
    /** Optional hint text shown below description. */
    hint?: string;
}

// ─── Section definition ───────────────────────────────────────────────

export interface SetupSection {
    key: string;
    label: string;
    minPlan: GestionPlan;
}

// ─── How-to / Tips items ──────────────────────────────────────────────

export interface HowToItem {
    id: string;
    title: string;
    description: string;
    href: string;
    minPlan: GestionPlan;
}

export interface TipItem {
    id: string;
    text: string;
    minPlan: GestionPlan;
    /** Optional CTA label (e.g., "Ver planes →"). */
    ctaLabel?: string;
    /** Optional CTA href. */
    ctaHref?: string;
}

// ─── Upgrade nudge ────────────────────────────────────────────────────

export interface UpgradeNudge {
    targetPlan: string;
    headline: string;
    body: string;
    ctaLabel: string;
    ctaHref: string;
}
