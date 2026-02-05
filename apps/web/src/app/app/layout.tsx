import { ReactNode } from 'react';
import { redirect } from 'next/navigation';

import { AppShell } from '@/components/app/app-shell';
import { getSession } from '@/lib/auth';
import type { Session } from '@/lib/auth/types';

export default async function AppLayout({ children }: { children: ReactNode }) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const resolvedSession = session as Session;

    const isSubscriptionActive = resolvedSession.subscription.status === 'active';
    if (!isSubscriptionActive) {
        redirect('/pricing');
    }

    return <AppShell session={resolvedSession}>{children}</AppShell>;
}
