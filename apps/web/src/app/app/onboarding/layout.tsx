import { ReactNode } from 'react';
import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import type { Session } from '@/lib/auth/types';

/**
 * Onboarding layout — minimal shell for the authenticated onboarding funnel.
 *
 * Design rules:
 *   - No AppShell sidebar (user has no active subscription yet).
 *   - No billing enforcement gate (this IS the onboarding path).
 *   - Unauthenticated users are sent to /entrar.
 *   - Users whose business is no longer in 'onboarding' are redirected to /app
 *     so they don't land on an already-completed flow.
 *   - Bypass: this route group is already added to billingBypassPaths in AppLayout
 *     so the parent gate never blocks it.
 *
 * Step indicator is rendered inline and driven by the `step` param passed
 * between server components via searchParams on individual step pages.
 */
export default async function OnboardingLayout({ children }: { children: ReactNode }) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const resolvedSession = session as Session;
    const businessStatus = resolvedSession.current?.business?.status;

    // If the user's business has already left onboarding, skip the funnel.
    if (businessStatus && businessStatus !== 'onboarding') {
        redirect('/app');
    }

    return (
        <div className="min-h-dvh flex flex-col bg-slate-50">
            {/* Minimal top bar — no sidebar, no nav links */}
            <header className="h-14 flex items-center px-6 border-b border-slate-200 bg-white shrink-0">
                <span className="text-sm font-semibold text-slate-800 tracking-tight">
                    Mi Rubro — Configuración inicial
                </span>
            </header>

            <main className="flex-1 flex flex-col items-center justify-start py-12 px-4">
                {children}
            </main>
        </div>
    );
}
