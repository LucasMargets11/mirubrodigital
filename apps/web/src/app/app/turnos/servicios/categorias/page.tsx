import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';

import { AppointmentCategoriesClient } from './categories-client';

export default async function TurnosCategoriasPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canManage = session.permissions?.manage_appointments ?? false;

    return <AppointmentCategoriesClient canManage={canManage} />;
}
