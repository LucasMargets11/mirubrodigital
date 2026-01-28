import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';

import { MenuClient } from './menu-client';

export default async function MenuPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.resto_menu !== false;
    const canView = session.permissions?.view_menu ?? false;

    if (!featureEnabled || !canView) {
        redirect('/app/servicios');
    }

    const canManage = session.permissions?.manage_menu ?? false;
    const canImport = session.permissions?.import_menu ?? false;
    const canExport = session.permissions?.export_menu ?? false;

    return <MenuClient canManage={canManage} canImport={canImport} canExport={canExport} />;
}
