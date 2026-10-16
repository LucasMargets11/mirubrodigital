import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';

import { ServicesClient } from './services-client';

export default async function TurnosServiciosPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canManage = session.permissions?.manage_appointments ?? false;

    return <ServicesClient canManage={canManage} />;
}
