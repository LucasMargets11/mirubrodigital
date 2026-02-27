import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { MenuClient } from '@/app/app/carta/menu-client';

export default async function MenuHomePage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    // Allow both QR menu plans (menu_builder) and restaurant plans (resto_menu)
    const featureEnabled =
        session.features?.menu_builder === true || session.features?.resto_menu === true;
    const canView = session.permissions?.view_menu ?? false;

    if (!featureEnabled || !canView) {
        redirect('/app/servicios');
    }

    const canManage = session.permissions?.manage_menu ?? false;
    const canImport = session.permissions?.import_menu ?? false;
    const canExport = session.permissions?.export_menu ?? false;
    const PLANS_WITH_IMAGES = ['menu_qr_visual', 'menu_qr_marca', 'plus'];
    const canUploadImages =
        session.features?.menu_item_images === true ||
        PLANS_WITH_IMAGES.includes(session.subscription?.plan ?? '');

    return (
        <MenuClient
            canManage={canManage}
            canImport={canImport}
            canExport={canExport}
            canUploadImages={canUploadImages}
        />
    );
}
