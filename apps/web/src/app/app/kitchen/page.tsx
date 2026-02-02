import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';

import { KitchenView } from './kitchen-view';

export const metadata = {
    title: 'Cocina en Vivo',
};

export default async function KitchenBoardPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.resto_kitchen !== false;
    const canView = session.permissions?.view_kitchen_board ?? false;

    if (!featureEnabled || !canView) {
        redirect('/app/servicios');
    }

    return <KitchenView />;
}
