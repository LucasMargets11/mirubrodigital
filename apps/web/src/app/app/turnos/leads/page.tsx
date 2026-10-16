import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { resolveLeadsAccess } from '@/features/leads/access';
import { getSession } from '@/lib/auth';

import { LeadsInboxClient } from './leads-inbox-client';

export default async function LeadsPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const access = resolveLeadsAccess(session);

    if (access === 'no_plan') {
        return (
            <AccessMessage
                title="Tu plan no incluye Leads"
                description="La bandeja de consultas del agente de WhatsApp está disponible en Turnos Base."
            />
        );
    }

    if (access === 'no_permission') {
        return (
            <AccessMessage
                title="Sin acceso"
                description="Tu rol no puede ver la bandeja de Leads."
                hint="Solicitá permisos a un administrador"
            />
        );
    }

    return (
        <LeadsInboxClient
            currentUserId={session.user?.id ?? null}
            businessTimeZone={session.current?.business?.timezone ?? null}
        />
    );
}
