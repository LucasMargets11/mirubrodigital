import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';

import { MenuClient } from './menu-client';

export default async function MenuPage() {
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
    // Feature-gated: QR Visual / QR Marca plans have menu_item_images flag.
    // Fall back to checking the plan code directly in case the features dict
    // is stale (e.g. Django process loaded old features.py before our changes).
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
