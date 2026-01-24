import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

import { StockClient } from './stock-client';
import { StockNav } from './stock-nav';

type GestionStockPageProps = {
    searchParams?: Record<string, string | string[] | undefined>;
};

export default async function GestionStockPage({ searchParams }: GestionStockPageProps) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.inventory !== false;
    const canView = session.permissions?.view_stock ?? false;
    const canManage = session.permissions?.manage_stock ?? false;

    if (!featureEnabled) {
        return <AccessMessage title="Tu plan no incluye Stock" description="Actualizá el plan para habilitar inventario en tiempo real." />;
    }

    if (!canView) {
        return <AccessMessage title="Sin acceso" description="Tu rol no puede ver el inventario." hint="Pedí acceso a un administrador" />;
    }

    const initialStatus = typeof searchParams?.status === 'string' ? searchParams.status : '';
    const initialAction = typeof searchParams?.action === 'string' ? searchParams.action : undefined;
    const initialProductId = typeof searchParams?.product === 'string' ? searchParams.product : undefined;

    return (
        <section className="space-y-6">
            <StockNav />
            <StockClient canManage={canManage} initialStatus={initialStatus} initialAction={initialAction} initialProductId={initialProductId} />
        </section>
    );
}
