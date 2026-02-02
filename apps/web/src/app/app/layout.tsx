import { ReactNode } from 'react';
import { redirect } from 'next/navigation';

import { Sidebar } from '@/components/navigation/sidebar';
import { Topbar } from '@/components/navigation/topbar';
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

    return (
        <div className="flex min-h-screen bg-slate-50">
            <Sidebar
                businessName={resolvedSession.current.business.name}
                service={resolvedSession.current.service}
                features={resolvedSession.features}
                permissions={resolvedSession.permissions}
            />
            <div className="flex flex-1 flex-col overflow-hidden">
                <Topbar
                    userName={resolvedSession.user.name}
                    role={resolvedSession.current.role}
                    businessName={resolvedSession.current.business.name}
                    subscriptionStatus={resolvedSession.subscription.status}
                    service={resolvedSession.current.service}
                />
                <main className="flex-1 space-y-6 overflow-y-auto p-6">{children}</main>
            </div>
        </div>
    );
}
