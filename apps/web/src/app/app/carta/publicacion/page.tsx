import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import { serverApiFetch } from '@/lib/api/server';
import type { MenuQrResponse } from '@/features/menu/types';

import { PublicacionClient } from './publicacion-client';

export default async function PublicacionPage() {
    const session = await getSession();
    if (!session) redirect('/entrar');

    const canView = session.permissions?.view_menu ?? false;
    if (!canView) redirect('/app/servicios');

    const businessId = session.current.business.id;
    const businessName = session.current.business.name;
    const customDomainAllowed = session.features?.menu_custom_domain === true;

    let qrData: MenuQrResponse | null = null;
    try {
        qrData = await serverApiFetch<MenuQrResponse>(`/api/v1/menu-qr/${businessId}/`);
    } catch {
        // QR not generated yet
    }

    return (
        <PublicacionClient
            businessId={businessId}
            businessName={businessName}
            initialQrData={qrData}
            customDomainAllowed={customDomainAllowed}
        />
    );
}
