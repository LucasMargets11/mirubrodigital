import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';

import { OrderEditClient } from './order-edit-client';

type OrderDetailPageProps = {
    params: {
        orderId: string;
    };
};

export default async function OrderDetailPage({ params }: OrderDetailPageProps) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.resto_orders !== false;
    const canViewOrders = session.permissions?.view_orders ?? false;

    if (!featureEnabled || !canViewOrders) {
        redirect('/app/servicios');
    }

    const canUpdate = session.permissions?.create_orders ?? false;
    const canClose = session.permissions?.close_orders ?? false;
    const canAssignTable = session.permissions?.manage_order_table ?? false;
    const canViewCommercialSettings = session.permissions?.view_commercial_settings ?? false;

    return (
        <OrderEditClient
            orderId={params.orderId}
            canUpdate={canUpdate}
            canClose={canClose}
            canAssignTable={canAssignTable}
            canViewCommercialSettings={canViewCommercialSettings}
        />
    );
}
