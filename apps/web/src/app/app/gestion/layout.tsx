import { ReactNode } from 'react';
import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import type { Session } from '@/lib/auth/types';

export default async function GestionLayout({ children }: { children: ReactNode }) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const resolvedSession = session as Session;
    const hasGestionService = resolvedSession.services.enabled.includes('gestion');
    const canViewGestion = resolvedSession.permissions?.view_dashboard ?? false;

    if (!hasGestionService || !canViewGestion) {
        redirect('/app/servicios');
    }

    return (
        <section className="space-y-6">{children}</section>
    );
}
