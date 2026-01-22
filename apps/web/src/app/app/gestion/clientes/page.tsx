import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

import { CustomersClient } from './customers-client';

export default async function GestionClientesPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const customersFeatureEnabled = session.features?.sales !== false;
    const canViewCustomers = session.permissions?.view_customers ?? false;
    const canManageCustomers = session.permissions?.manage_customers ?? false;
    const canCreateCustomers = canManageCustomers || (session.permissions?.create_sales ?? false);

    if (!customersFeatureEnabled) {
        return <AccessMessage title="Tu plan no incluye Clientes" description="Actualizá el plan para gestionar clientes." />;
    }

    if (!canViewCustomers) {
        return (
            <AccessMessage
                title="Sin acceso"
                description="Tu rol no puede ver el padrón de clientes."
                hint="Solicitá permisos a un administrador"
            />
        );
    }

    return <CustomersClient canCreate={canCreateCustomers} canManage={canManageCustomers} />;
}
