import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

import { SalesClient } from './sales-client';

export default async function GestionVentasPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.sales !== false;
    const canView = session.permissions?.view_sales ?? false;
    const canCreate = session.permissions?.create_sales ?? false;
    const canViewQuotes = session.permissions?.view_quotes ?? false;
    const canCreateQuotes = session.permissions?.create_quotes ?? false;

    if (!featureEnabled) {
        return <AccessMessage title="Tu plan no incluye Ventas" description="Actualizá tu plan para habilitar el módulo de ventas." />;
    }

    if (!canView) {
        return <AccessMessage title="Sin acceso" description="Tu rol no puede ver las ventas." hint="Pedí acceso a un administrador" />;
    }

    return <SalesClient canCreate={canCreate} canViewQuotes={canViewQuotes} canCreateQuotes={canCreateQuotes} />;
}
