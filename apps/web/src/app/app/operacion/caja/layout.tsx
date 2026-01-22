import { ReactNode } from 'react';
import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';
import type { Session } from '@/lib/auth/types';

import { OperacionCajaNav } from './navigation';

type LayoutProps = {
    children: ReactNode;
};

export default async function OperacionCajaLayout({ children }: LayoutProps) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const resolvedSession = session as Session;
    const featureEnabled = resolvedSession.features?.cash !== false;
    const canView = resolvedSession.permissions?.view_cash ?? false;
    const canManage = resolvedSession.permissions?.manage_cash ?? false;

    if (!featureEnabled) {
        return (
            <AccessMessage
                title="Actualizá tu plan"
                description="Tu plan actual no incluye el módulo de caja."
                hint="Contactá a un administrador para habilitarlo"
            />
        );
    }

    if (!canView) {
        return (
            <AccessMessage
                title="Sin acceso a Caja"
                description="Tu rol no tiene permisos para ver la operación de caja."
                hint="Pedí acceso al administrador del negocio"
            />
        );
    }

    const tabs = [
        { href: '/app/operacion/caja', label: 'Caja (hoy)' },
        ...(canManage
            ? [
                { href: '/app/operacion/caja/movimientos', label: 'Movimientos' },
                { href: '/app/operacion/caja/cierre', label: 'Cierre' },
            ]
            : []),
    ];

    return (
        <section className="space-y-6">
            <OperacionCajaNav tabs={tabs} />
            <div className="space-y-6">{children}</div>
        </section>
    );
}
