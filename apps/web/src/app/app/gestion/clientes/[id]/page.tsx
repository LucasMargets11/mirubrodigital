import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

import { CustomerDetailClient } from './customer-detail-client';

type Props = {
    params: Promise<{ id: string }>;
};

export default async function CustomerDetailPage({ params }: Props) {
    const { id } = await params;
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const customersFeatureEnabled = session.features?.sales !== false;
    const canViewCustomers = session.permissions?.view_customers ?? false;
    const canViewSales = session.permissions?.view_sales ?? false;
    const canManageCustomers = session.permissions?.manage_customers ?? false;
    const quotesFeatureEnabled = session.features?.quotes !== false;
    const canViewQuotes = session.permissions?.view_quotes ?? false;

    if (!customersFeatureEnabled) {
        return <AccessMessage title="Tu plan no incluye Clientes" description="Actualizá el plan para gestionar clientes." />;
    }

    if (!canViewCustomers) {
        return (
            <AccessMessage
                title="Sin acceso"
                description="Tu rol no puede ver la ficha del cliente."
                hint="Solicitá permisos a un administrador"
            />
        );
    }

    return (
        <CustomerDetailClient
            customerId={id}
            canManage={canManageCustomers}
            canViewSales={canViewSales}
            canViewQuotes={quotesFeatureEnabled && canViewQuotes}
        />
    );
}
