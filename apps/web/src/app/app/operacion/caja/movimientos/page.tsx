import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';
import type { Session } from '@/lib/auth/types';

import { MovimientosClient } from './movimientos-client';

export default async function OperacionCajaMovimientosPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const resolvedSession = session as Session;
    const canManage = resolvedSession.permissions?.manage_cash ?? false;

    if (!canManage) {
        return (
            <AccessMessage
                title="No podés cargar movimientos"
                description="Tu rol no puede operar la caja."
                hint="Pedile acceso a un administrador"
            />
        );
    }

    return <MovimientosClient canManage={canManage} />;
}
