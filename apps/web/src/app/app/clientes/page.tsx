import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { BusinessNotificationsPanel } from '@/features/business-notifications';
import { getSession } from '@/lib/auth';

import { CustomersClient } from './customers-client';

export default async function ClientesPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    // Clientes core es compartido: Gestión (gate histórico por `sales`) o
    // cualquier plan con el flag `customers` (incluye Turnos, CUSTOMER 02).
    const customersFeatureEnabled = session.features?.customers === true || session.features?.sales !== false;
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

    // CUSTOMER 07C: los avisos de recordatorios vencidos también se ven acá
    // (mismo panel que Turnos; los negocios solo-Gestión no entran a Turnos).
    return (
        <div className="space-y-4">
            <BusinessNotificationsPanel />
            <CustomersClient canCreate={canCreateCustomers} canManage={canManageCustomers} />
        </div>
    );
}
