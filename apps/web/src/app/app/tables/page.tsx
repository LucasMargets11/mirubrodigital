import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';

import { TablesClient } from './tables-client';

export default async function TablesPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.resto_tables !== false;
    const canView = session.permissions?.view_tables ?? false;

    if (!featureEnabled || !canView) {
        redirect('/app/servicios');
    }

    return <TablesClient />;
}
