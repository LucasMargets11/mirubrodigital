import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { MenuClient } from '@/app/app/carta/menu-client';

export default async function MenuHomePage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canView = session.permissions?.view_menu ?? false;
    if (!canView) {
        redirect('/app/servicios');
    }

    const canManage = session.permissions?.manage_menu ?? false;
    const canImport = session.permissions?.import_menu ?? false;
    const canExport = session.permissions?.export_menu ?? false;

    return <MenuClient canManage={canManage} canImport={canImport} canExport={canExport} />;
}
