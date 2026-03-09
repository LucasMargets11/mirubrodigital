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
 *   no_subscription / checkout_pending → redirect to /app/planes to complete onboarding
 *   suspended / grace_period_expired / canceled / trial_expired
 *                                      → redirect to /app/planes for regularization
 *
 * Bypass: /app/planes and /app/servicios are always accessible so users can
 * regularize or complete their subscription — the redirect target must not
 * itself be behind the gate.
 */
export default async function AppLayout({ children }: { children: ReactNode }) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const resolvedSession = session as Session;
    const sub = resolvedSession.subscription;

    // Paths that must remain accessible regardless of billing state.
    // These are the "regularization exits" — if we redirect here from the gate,
    // they must not trigger another redirect.
    const headersList = await headers();
    const pathname = headersList.get('x-pathname') ?? headersList.get('x-invoke-path') ?? '';
    const billingBypassPaths = ['/app/planes', '/app/servicios'];
    const isBillingBypass = billingBypassPaths.some((p) => pathname.startsWith(p));

    // Use access_allowed from the backend enforcement layer, not raw status.
    // access_allowed=true covers: active, trialing, past_due-within-grace.
    if (!sub.access_allowed && !isBillingBypass) {
        redirect('/app/planes');
    }

    return <AppShell session={resolvedSession}>{children}</AppShell>;
}
