import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';
import type { Session } from '@/lib/auth/types';

import { CierreClient } from './cierre-client';

export default async function OperacionCajaCierrePage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const resolvedSession = session as Session;
    const canManage = resolvedSession.permissions?.manage_cash ?? false;

    if (!canManage) {
        return (
            <AccessMessage
                title="No podés cerrar la caja"
                description="Tu rol no tiene permisos para realizar el arqueo."
                hint="Pedí acceso a un administrador"
            />
        );
    }

    return <CierreClient canManage={canManage} />;
}
