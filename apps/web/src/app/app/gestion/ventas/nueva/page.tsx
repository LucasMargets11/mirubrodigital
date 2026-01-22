import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

import { NewSaleClient } from '../new-sale-client';

export default async function GestionNuevaVentaPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.sales !== false;
    const canView = session.permissions?.view_sales ?? false;
    const canCreate = session.permissions?.create_sales ?? false;

    if (!featureEnabled) {
        return <AccessMessage title="Tu plan no incluye Ventas" description="Actualizá tu plan para habilitar ventas." />;
    }

    if (!canView || !canCreate) {
        return (
            <AccessMessage
                title="Sin acceso"
                description="Tu rol no tiene permiso para registrar ventas."
                hint="Pedí acceso a un administrador"
            />
        );
    }

    return <NewSaleClient />;
}
