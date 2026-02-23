import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

import { StockClient } from './stock-client';
import { StockNav } from './stock-nav';

type GestionStockPageProps = {
    searchParams?: Promise<Record<string, string | string[] | undefined>>;
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

    const resolvedParams = searchParams ? await searchParams : {};
    const initialStatus = typeof resolvedParams?.status === 'string' ? resolvedParams.status : '';
    const initialAction = typeof resolvedParams?.action === 'string' ? resolvedParams.action : undefined;
    const initialProductId = typeof resolvedParams?.product === 'string' ? resolvedParams.product : undefined;

    return (
        <section className="space-y-6">
            <StockNav />
            <StockClient canManage={canManage} initialStatus={initialStatus} initialAction={initialAction} initialProductId={initialProductId} />
        </section>
    );
}
