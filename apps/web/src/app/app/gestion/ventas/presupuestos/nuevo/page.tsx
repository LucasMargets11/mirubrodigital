import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';
import { NewQuoteClient } from './new-quote-client';

export default async function NuevoPresupuestoPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.sales !== false;
    const canCreate = session.permissions?.create_quotes ?? false;

    if (!featureEnabled) {
        return <AccessMessage title="Tu plan no incluye Ventas" description="Actualizá tu plan para habilitar ventas." />;
    }

    if (!canCreate) {
        return (
            <AccessMessage
                title="Sin acceso"
                description="Tu rol no tiene permiso para crear presupuestos."
                hint="Pedí acceso a un administrador"
            />
        );
    }

    return <NewQuoteClient />;
}
