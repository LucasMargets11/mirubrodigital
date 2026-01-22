import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

import { InvoicesClient } from './invoices-client';

export default async function GestionFacturasPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.invoices !== false;
    const canView = session.permissions?.view_invoices ?? false;
    const canIssue = session.permissions?.issue_invoices ?? false;

    if (!featureEnabled) {
        return <AccessMessage title="Tu plan no incluye Facturas" description="Actualizá tu plan para emitir comprobantes digitales." />;
    }

    if (!canView) {
        return <AccessMessage title="Sin acceso" description="Tu rol no puede ver las facturas." hint="Pedí acceso a un administrador" />;
    }

    return <InvoicesClient canIssue={canIssue} />;
}
