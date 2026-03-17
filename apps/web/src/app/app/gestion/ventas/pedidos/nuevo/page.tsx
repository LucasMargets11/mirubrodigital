import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

import { NewOrderClient } from '../new-order-client';

export default async function GestionNuevoPedidoPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    // Check features and permissions
    const hasSalesFeature = session.features?.sales !== false;
    // Orders might be a sub-feature or separate. Assuming sales is base.
    const hasOrdersFeature = session.features?.orders !== false; // if undefined, it's allowed
    
    const canView = session.permissions?.view_orders ?? false;
    const canCreate = session.permissions?.create_orders ?? false;

    if (!hasSalesFeature || !hasOrdersFeature) {
        return <AccessMessage title="Tu plan no incluye Pedidos" description="Actualizá tu plan para habilitar el módulo de pedidos." />;
    }

    if (!canView || !canCreate) {
        return (
            <AccessMessage
                title="Sin acceso"
                description="Tu rol no tiene permiso para crear pedidos."
                hint="Ped� acceso a un administrador"
            />
        );
    }

    return <NewOrderClient />;
}
