import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { AppPageHeader } from '@/components/navigation/app-page-header';
import { getSession } from '@/lib/auth';

import { HorariosClient } from './horarios-client';

export default async function TurnosHorariosPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canView = session.permissions?.view_appointments ?? false;

    if (!canView) {
        return (
            <AccessMessage
                title="Sin acceso"
                description="Tu rol no tiene permiso para ver los horarios de Turnos."
                hint="Pedí acceso a un administrador"
            />
        );
    }

    const canManage = session.permissions?.manage_appointments ?? false;

    return (
        <section className="space-y-4">
            <AppPageHeader
                title="Horarios"
                description="Configurá el horario general del negocio, el horario por profesional y las excepciones por fecha."
            />
            <HorariosClient canManage={canManage} />
        </section>
    );
}
