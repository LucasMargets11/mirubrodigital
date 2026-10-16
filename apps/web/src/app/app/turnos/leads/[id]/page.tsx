import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { resolveLeadsAccess } from '@/features/leads/access';
import { getSession } from '@/lib/auth';

import { LeadDetailClient } from './lead-detail-client';

type Props = {
    params: Promise<{ id: string }>;
};

/**
 * Detalle operativo del Lead (LEADS 05B). Mismo gating que la bandeja
 * (`appointments.leads` + `view_leads`); las acciones solo con `manage_leads`.
 * Los selectores de Customer/turno reutilizan APIs que exigen sus propios
 * permisos (`view_customers` / `view_appointments`). Todo es UX: el backend
 * vuelve a validar cada request.
 */
export default async function LeadDetailPage({ params }: Props) {
    const { id } = await params;
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
                description="Tu rol no puede ver los Leads."
                hint="Solicitá permisos a un administrador"
            />
        );
    }

    // Mismo criterio que la ficha de cliente (`/app/clientes/[id]`).
    const customersFeatureEnabled = session.features?.customers === true || session.features?.sales !== false;
    const canViewCustomers = customersFeatureEnabled && (session.permissions?.view_customers ?? false);

    return (
        <LeadDetailClient
            leadId={id}
            canManage={session.permissions?.manage_leads ?? false}
            canViewCustomers={canViewCustomers}
            canViewAppointments={session.permissions?.view_appointments ?? false}
            currentUserId={session.user?.id ?? null}
            businessTimeZone={session.current?.business?.timezone ?? null}
        />
    );
}
