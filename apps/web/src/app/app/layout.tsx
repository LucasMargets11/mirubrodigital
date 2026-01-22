import { ReactNode } from 'react';
import { headers } from 'next/headers';
import { redirect } from 'next/navigation';

import { Sidebar } from '@/components/navigation/sidebar';
import { Topbar } from '@/components/navigation/topbar';
import { getSession } from '@/lib/auth';
import type { Session } from '@/lib/auth/types';

function isPlanRoute(): boolean {
    const headersList = headers();
    const candidates: string[] = [];
    const possibleHeaderKeys = ['x-invoke-path', 'x-pathname', 'x-forwarded-path', 'x-forwarded-uri'];

    possibleHeaderKeys.forEach((key) => {
        const value = headersList.get(key);
        if (value) {
            candidates.push(value);
        }
    });

    const nextUrl = headersList.get('next-url');
    if (nextUrl) {
        try {
            candidates.push(new URL(nextUrl, 'http://localhost').pathname);
        } catch (error) {
            // ignore parsing issues and fallback to other hints
        }
    }

    return candidates.some((path) => path?.startsWith('/app/planes'));
}

export default async function AppLayout({ children }: { children: ReactNode }) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const resolvedSession = session as Session;

    const isSubscriptionActive = resolvedSession.subscription.status === 'active';
    if (!isSubscriptionActive && !isPlanRoute()) {
        redirect('/app/planes');
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
