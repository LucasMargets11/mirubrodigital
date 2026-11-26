import { ReactNode } from 'react';
import { headers } from 'next/headers';
import { redirect } from 'next/navigation';

import { receptionLeadsPathFor } from '@/features/leads/ui/leads-routes';
import { getSession } from '@/lib/auth';
import type { Session } from '@/lib/auth/types';

export default async function TurnosLayout({ children }: { children: ReactNode }) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const resolvedSession = session as Session;
    const hasService = resolvedSession.services.enabled.includes('appointments');

    if (!hasService) {
        // PROD-02G2: un negocio con Recepcionista IA y sin Turnos sigue los
        // deep links de Leads (bookmarks, notificaciones `/app/turnos/leads/{id}`)
        // a su módulo. Sin bucle: `/app/recepcionista` exige `reception`.
        if (resolvedSession.services.enabled.includes('reception')) {
            const headersList = await headers();
            const pathname = headersList.get('x-pathname') ?? headersList.get('x-invoke-path') ?? '';
            const receptionPath = receptionLeadsPathFor(pathname);
            if (receptionPath) {
                redirect(receptionPath as never);
            }
        }
        redirect('/app/servicios');
    }

    return (
        <section className="space-y-6">
            {children}
        </section>
    );
}
