import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { MenuQrPageClient } from './menu-qr-client';

export default async function MenuQrPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canView = session.permissions?.view_menu_admin ?? session.permissions?.view_menu ?? false;
    if (!canView) {
        redirect('/app/servicios');
    }

    return (
        <MenuQrPageClient
            businessId={session.current.business.id}
            businessName={session.current.business.name}
        />
    );
}
