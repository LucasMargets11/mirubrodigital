import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { AppPageHeader } from '@/components/navigation/app-page-header';
import { getSession } from '@/lib/auth';

import { ProfessionalsClient } from './professionals-client';

export default async function TurnosProfesionalesPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canView = session.permissions?.view_appointments ?? false;

    if (!canView) {
        return (
            <AccessMessage
                title="Sin acceso"
                description="Tu rol no tiene permiso para ver los profesionales de Turnos."
                hint="Pedí acceso a un administrador"
            />
        );
    }

    const canManage = session.permissions?.manage_appointments ?? false;

    return (
        <section className="space-y-4">
            <AppPageHeader
                title="Profesionales"
                description="Profesionales que realizan tus servicios de Turnos. Es opcional: si no cargás ninguno, la reserva se hace directamente contra el negocio."
            />
            <ProfessionalsClient canManage={canManage} />
        </section>
    );
}
