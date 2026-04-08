import { ReactNode } from 'react';
import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import type { Session } from '@/lib/auth/types';
import { ResenasNav } from './resenas-nav';

export default async function ResenasLayout({ children }: { children: ReactNode }) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const resolvedSession = session as Session;
    const hasService = resolvedSession.services.enabled.includes('qr_reviews');

    if (!hasService) {
        redirect('/app/servicios');
    }

    return (
        <section className="space-y-6">
            <ResenasNav />
            {children}
        </section>
    );
}
