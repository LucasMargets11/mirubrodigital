import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

import { OrdersClient } from './orders-client';

export default async function GestionPedidosPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.sales !== false; // Assuming Sales feature covers Orders
    // Using granular permissions as requested
    const canView = session.permissions?.view_orders ?? session.permissions?.view_sales ?? false;
    const canCreate = session.permissions?.create_orders ?? session.permissions?.create_sales ?? false;

    if (!featureEnabled) {
        return <AccessMessage title="Tu plan no incluye Pedidos" description="Actualizá tu plan para habilitar el módulo de pedidos." />;
    }

    if (!canView) {
        return <AccessMessage title="Sin acceso" description="Tu rol no puede ver los pedidos." hint="Pedí acceso a un administrador" />;
    }

    const quotesFeatureEnabled = session.features?.quotes !== false;
    const canViewQuotes = (session.permissions?.view_quotes ?? false) && quotesFeatureEnabled;

    return <OrdersClient canCreate={canCreate} canViewQuotes={canViewQuotes} />;
}
