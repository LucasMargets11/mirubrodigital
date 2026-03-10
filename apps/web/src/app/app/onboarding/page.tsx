import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { serverApiFetch } from '@/lib/api/server';

/**
 * Onboarding smart router — Wave 4.
 *
 * This server component is the canonical entry point for the onboarding funnel.
 * All paths that previously pointed to /app/onboarding/servicio now point here.
 *
 * It fetches the current onboarding step from the backend and redirects the
 * user to the correct step page, providing resume semantics for users who
 * close the browser mid-funnel.
 *
 * Step → Route mapping:
 *   no_service_type   → /app/onboarding/servicio   (choose service type)
 *   plan_selection    → /app/onboarding/plan        (choose plan)
 *   checkout_pending  → /app/onboarding/checkout?plan=<code>  (MP payment + polling)
 *   done              → /app                         (already active — leave funnel)
 *
 * Fallback (error / no business): /app/onboarding/servicio (safe default).
 *
 * The parent onboarding/layout.tsx already validates the session and redirects
 * non-onboarding businesses to /app, so this page can assume:
 *   1. The user is authenticated.
 *   2. business.status === 'onboarding' (or layout already redirected away).
 */

type OnboardingStatus = {
    step: 'no_service_type' | 'plan_selection' | 'checkout_pending' | 'done';
    checkout_session_id: string | null;
    pending_plan_code: string | null;
    service_type: string | null;
    email_verified: boolean;
    can_proceed: boolean;
};

// Route constants — avoid typed-route literal checks on pages whose types
// haven't been regenerated yet by the Next.js compilation step.
const ROUTE_SERVICIO      = '/app/onboarding/servicio'   as never;
const ROUTE_PLAN          = '/app/onboarding/plan'       as never;
const ROUTE_CHECKOUT_BASE = '/app/onboarding/checkout'   as never;
const ROUTE_APP           = '/app'                       as never;

export default async function OnboardingIndexPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar' as never);
    }

    let onboardingStatus: OnboardingStatus | null = null;
    try {
        onboardingStatus = await serverApiFetch<OnboardingStatus>('/api/v1/auth/onboarding/');
    } catch {
        // API error — fall through to safe default below.
    }

    if (!onboardingStatus) {
        // Cannot determine step — send to step 1 as safe default.
        redirect(ROUTE_SERVICIO);
    }

    const { step, pending_plan_code } = onboardingStatus;

    switch (step) {
        case 'done':
            // Business is already active — leave the onboarding funnel.
            redirect(ROUTE_APP);

        case 'checkout_pending': {
            // Checkout already initiated — resume at the checkout/polling page.
            // Pass the plan_code so the checkout page can call start-checkout
            // idempotently and recover the existing init_point.
            const planParam = pending_plan_code
                ? `?plan=${encodeURIComponent(pending_plan_code)}`
                : '';
            redirect((`${ROUTE_CHECKOUT_BASE}${planParam}`) as never);
        }

        case 'plan_selection':
            // Service selected — user needs to pick a plan.
            redirect(ROUTE_PLAN);

        case 'no_service_type':
        default:
            // No service selected yet — start at step 1.
            redirect(ROUTE_SERVICIO);
    }
}
