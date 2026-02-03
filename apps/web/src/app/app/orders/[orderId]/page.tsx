import { notFound, redirect } from 'next/navigation';

import type { Order } from '@/features/orders/types';
import { serverApiFetch } from '@/lib/api/server';
import { getSession } from '@/lib/auth';

import { OrderEditClient } from './order-edit-client';

type OrderDetailPageProps = {
    params: Promise<{
        orderId: string;
    }>;
};

export default async function OrderDetailPage({ params }: OrderDetailPageProps) {
    const { orderId } = await params;
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
    const invoicesFeatureEnabled = session.features?.invoices !== false;
    const canViewInvoices = session.permissions?.view_invoices ?? false;
    const canIssueInvoices = session.permissions?.issue_invoices ?? false;

    let order: Order | null = null;
    try {
        order = await serverApiFetch<Order>(`/api/v1/orders/${orderId}/`);
    } catch (error) {
        notFound();
    }

    if (!order) {
        notFound();
    }

    return (
        <OrderEditClient
            orderId={orderId}
            initialOrder={order}
            canUpdate={canUpdate}
            canClose={canClose}
            canAssignTable={canAssignTable}
            canViewCommercialSettings={canViewCommercialSettings}
            invoicesFeatureEnabled={invoicesFeatureEnabled}
            canIssueInvoices={canIssueInvoices}
            canViewInvoices={canViewInvoices}
        />
    );
}
