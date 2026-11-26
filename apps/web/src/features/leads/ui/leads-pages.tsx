import { redirect } from 'next/navigation';
import type { ReactElement } from 'react';

import { AccessMessage } from '@/components/app/access-message';
import { resolveLeadsAccess } from '@/features/leads/access';
import { getSession } from '@/lib/auth';
import type { Session } from '@/lib/auth/types';

import { LeadDetailClient } from './lead-detail-client';
import { LeadsInboxClient } from './leads-inbox-client';
import { LeadsContextProvider } from './leads-context';
import { RECEPTION_LEADS_BASE_PATH, TURNOS_LEADS_CONTEXT, type LeadsProduct, type LeadsRouteContext } from './leads-routes';

/**
 * PROD-02G2 — Cuerpo único (servidor) de la bandeja y del detalle de Leads,
 * montado por `/app/turnos/leads` y `/app/recepcionista/leads`. El gating es
 * el de LEADS 05A/05B (flag `leads` + `view_leads`; acciones con
 * `manage_leads`); el backend vuelve a validar cada request.
 */

const NO_PLAN_COPY: Record<LeadsProduct, string> = {
    appointments: 'La bandeja de consultas del agente de WhatsApp está disponible en Turnos Base.',
    reception: 'La bandeja de consultas del agente de WhatsApp no está incluida en tu plan de Recepcionista IA.',
};

/** Contexto del producto para la sesión actual. Recepcionista: agenda solo con `agenda_integration`. */
export function leadsContextFor(product: LeadsProduct, session: Session): LeadsRouteContext {
    if (product === 'reception') {
        return {
            basePath: RECEPTION_LEADS_BASE_PATH,
            agendaEnabled: session.features?.agenda_integration === true,
            product: 'reception',
        };
    }
    return TURNOS_LEADS_CONTEXT;
}

/**
 * Turnos usa el contexto por defecto (sin provider: su salida queda idéntica a
 * la previa); Recepcionista monta el suyo.
 */
function withLeadsContext(product: LeadsProduct, session: Session, node: ReactElement): ReactElement {
    if (product === 'appointments') return node;
    return <LeadsContextProvider value={leadsContextFor(product, session)}>{node}</LeadsContextProvider>;
}

function denied(product: LeadsProduct, session: Session, noPermission: string) {
    const access = resolveLeadsAccess(session);
    if (access === 'no_plan') {
        return <AccessMessage title="Tu plan no incluye Leads" description={NO_PLAN_COPY[product]} />;
    }
    if (access === 'no_permission') {
        return <AccessMessage title="Sin acceso" description={noPermission} hint="Solicitá permisos a un administrador" />;
    }
    return null;
}

export async function renderLeadsInboxPage(product: LeadsProduct) {
    const session = await getSession();
    if (!session) {
        redirect('/entrar');
    }
    const blocked = denied(product, session, 'Tu rol no puede ver la bandeja de Leads.');
    if (blocked) return blocked;

    return withLeadsContext(product, session, (
        <LeadsInboxClient
            currentUserId={session.user?.id ?? null}
            businessTimeZone={session.current?.business?.timezone ?? null}
            canManage={session.permissions?.manage_leads ?? false}
            canManageAppointments={session.permissions?.manage_appointments ?? false}
            canViewAppointments={session.permissions?.view_appointments ?? false}
        />
    ));
}

export async function renderLeadDetailPage(product: LeadsProduct, leadId: string) {
    const session = await getSession();
    if (!session) {
        redirect('/entrar');
    }
    const blocked = denied(product, session, 'Tu rol no puede ver los Leads.');
    if (blocked) return blocked;

    // Mismo criterio que la ficha de cliente (`/app/clientes/[id]`).
    const customersFeatureEnabled = session.features?.customers === true || session.features?.sales !== false;
    const canViewCustomers = customersFeatureEnabled && (session.permissions?.view_customers ?? false);

    return withLeadsContext(product, session, (
        <LeadDetailClient
            leadId={leadId}
            canManage={session.permissions?.manage_leads ?? false}
            canManageAppointments={session.permissions?.manage_appointments ?? false}
            canViewCustomers={canViewCustomers}
            canViewAppointments={session.permissions?.view_appointments ?? false}
            currentUserId={session.user?.id ?? null}
            businessTimeZone={session.current?.business?.timezone ?? null}
        />
    ));
}
