import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';

import { TablesSettingsClient } from './tables-settings-client';

export default async function TablesSettingsPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.resto_tables !== false;
    const canManage = session.permissions?.manage_tables ?? false;

    if (!featureEnabled || !canManage) {
        redirect('/app/servicios');
    }

    return <TablesSettingsClient />;
}
