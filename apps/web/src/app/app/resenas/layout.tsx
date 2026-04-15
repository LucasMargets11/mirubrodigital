import { ReactNode } from 'react';
import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import type { Session } from '@/lib/auth/types';

export default async function ResenasLayout({ children }: { children: ReactNode }) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const resolvedSession = session as Session;
    const enabledServices = resolvedSession.services.enabled;
    const hasService =
        enabledServices.includes('qr_reviews') ||
        enabledServices.includes('qr_reviews_base') ||
        enabledServices.includes('qr_reviews_pro');

    if (!hasService) {
        redirect('/app/servicios');
    }

    return (
        <section className="space-y-6">
            {children}
        </section>
    );
}
