import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { canUploadMenuImages } from '@/features/menu/constants';

import { MenuClient } from '../menu-client';

export default async function CartaProductosPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    // Allow both restaurant plans (resto_menu) and QR menu plans (menu_builder)
    const featureEnabled =
        session.features?.menu_builder === true || session.features?.resto_menu === true;
    const canView = session.permissions?.view_menu ?? false;

    if (!featureEnabled || !canView) {
        redirect('/app/servicios');
    }

    const canManage = session.permissions?.manage_menu ?? false;
    const canImport = session.permissions?.import_menu ?? false;
    const canExport = session.permissions?.export_menu ?? false;
    const canUploadImages = canUploadMenuImages(
        session.features,
        session.subscription?.plan,
    );

    return (
        <MenuClient
            canManage={canManage}
            canImport={canImport}
            canExport={canExport}
            canUploadImages={canUploadImages}
        />
    );
}
