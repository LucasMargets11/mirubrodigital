import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';

import { NewOrderClient } from './new-order-client';

export default async function NewOrderPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.resto_orders !== false;
    const canCreate = session.permissions?.create_orders ?? false;

    if (!featureEnabled || !canCreate) {
        redirect('/app/servicios');
    }

    const canViewCommercialSettings = session.permissions?.view_commercial_settings ?? false;

    return <NewOrderClient canViewCommercialSettings={canViewCommercialSettings} />;
}
