import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';

import OnboardingWizard from './onboarding-wizard';

export default async function GestionOnboardingPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    // Only owners and admins may access the onboarding wizard
    if (!['owner', 'admin'].includes(session.current.role ?? '')) {
        redirect('/app/gestion/dashboard');
    }

    // Feature gate: rollout env var
    if (process.env.NEXT_PUBLIC_NEW_ONBOARDING_ENABLED !== 'true') {
        redirect('/app/gestion/dashboard');
    }

    return (
        <main className="min-h-screen bg-slate-50 px-4 py-8">
            <OnboardingWizard />
        </main>
    );
}
