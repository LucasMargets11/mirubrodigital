import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';

import { OrdersClient } from './orders-client';

export default async function OrdersPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.resto_orders !== false;
    const canView = session.permissions?.view_orders ?? false;

    if (!featureEnabled || !canView) {
        redirect('/app/servicios');
    }

    const canCreate = session.permissions?.create_orders ?? false;
    const canUpdate = session.permissions?.change_order_status ?? false;
    const canClose = session.permissions?.close_orders ?? false;

    return <OrdersClient canCreate={canCreate} canUpdate={canUpdate} canClose={canClose} />;
}
