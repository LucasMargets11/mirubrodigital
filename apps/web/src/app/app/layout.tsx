import { ReactNode } from 'react';
import { headers } from 'next/headers';
import { redirect } from 'next/navigation';

import { AppShell } from '@/components/app/app-shell';
import { getSession } from '@/lib/auth';
import type { Session } from '@/lib/auth/types';

/**
 * App layout — enforces subscription access gate.
 *
 * Enforcement policy (mirrors backend billing.enforcement):
 *   access_allowed=true                → render app normally
 *   reason_code='grace_period_active'  → render app + warn banner (handled in AppShell)
 *   no_subscription / checkout_pending → redirect to /app/onboarding/servicio (new users)
 *                                        or /app/planes (returning users)
 *   past_due (grace expired)           → redirect to /app/cuenta/estado?status=past_due
 *   suspended                          → redirect to /app/cuenta/estado?status=suspended
 *   canceled                           → redirect to /app/cuenta/estado?status=canceled
 *
 * Onboarding short-circuit (Wave 3):
 *   business.status='onboarding' AND access_allowed=false
 *     → redirect to /app/onboarding/servicio (authenticated guided funnel)
 *       so newly registered users land on service selection, not the billing hub.
 *
 * Allowed states (enter app normally):
 *   'active' | 'trialing' | 'past_due' (grace) → access_allowed=true → app shell
 *
 * Bypass: /app/planes, /app/servicios, /app/onboarding/*, and /app/cuenta/estado
 * are always accessible so users can regularize or complete their onboarding
 * without triggering another redirect.
 */
export default async function AppLayout({ children }: { children: ReactNode }) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const resolvedSession = session as Session;
    const sub = resolvedSession.subscription;
    const businessStatus = resolvedSession.current?.business?.status;

    // Force password change guard — must run before billing checks.
    // Users with must_change_password=true are redirected to the auth-layout
    // change-password page. This only applies to 'personal' account mode
    // users whose password was reset by the owner.
    if (resolvedSession.user.must_change_password) {
        redirect('/cambiar-contrasena');
    }

    // Paths that must remain accessible regardless of billing state.
    // /app/onboarding/*    — guided onboarding funnel (Wave 3)
    // /app/planes          — plan page for returning users
    // /app/servicios       — billing hub (kept as bypass for edge-case direct links)
    // /app/cuenta/estado   — state-specific blocked screens (Wave 5)
    const headersList = await headers();
    const pathname = headersList.get('x-pathname') ?? headersList.get('x-invoke-path') ?? '';
    const billingBypassPaths = ['/app/planes', '/app/servicios', '/app/onboarding', '/app/cuenta/estado'];
    const isBillingBypass = billingBypassPaths.some((p) => pathname.startsWith(p));

    if (!sub.access_allowed && !isBillingBypass) {
        // New users in 'onboarding' state → guided funnel (Wave 4).
        // Route to the smart onboarding index which determines the correct
        // step server-side (no_service_type / plan_selection / checkout_pending).
        if (businessStatus === 'onboarding') {
            redirect('/app/onboarding');
        }

        // Hard-blocked states: show a clear, dedicated state screen (Wave 5).
        // These users cannot use the app and should not land on /app/planes
        // which would show an actionable plan upgrade page with no context.
        if (businessStatus === 'suspended') {
            redirect('/app/cuenta/estado?status=suspended');
        }
        if (businessStatus === 'canceled') {
            redirect('/app/cuenta/estado?status=canceled');
        }
        // past_due with no access means grace period has expired.
        if (businessStatus === 'past_due') {
            redirect('/app/cuenta/estado?status=past_due');
        }

        redirect('/app/planes');
    }

    // Onboarding routes have their own dedicated minimal shell (OnboardingLayout).
    // Rendering AppShell here would inject the full sidebar around it even though
    // the user has not completed service selection or activated a plan.
    // Skip AppShell entirely for /app/onboarding/* — the nested layout owns the UX.
    if (pathname.startsWith('/app/onboarding')) {
        return <>{children}</>;
    }

    return <AppShell session={resolvedSession}>{children}</AppShell>;
}
