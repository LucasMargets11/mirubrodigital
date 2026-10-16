import { redirect } from 'next/navigation';
import { ReactNode } from 'react';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

import { ServicesLayout } from './services-layout';

export default async function TurnosServiciosLayout({ children }: { children: ReactNode }) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canView = session.permissions?.view_appointments ?? false;

    if (!canView) {
        return (
            <AccessMessage
                title="Sin acceso"
                description="Tu rol no tiene permiso para ver los servicios de Turnos."
                hint="Pedí acceso a un administrador"
            />
        );
    }

    return <ServicesLayout>{children}</ServicesLayout>;
}
