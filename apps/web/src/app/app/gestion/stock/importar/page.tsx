import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

import { StockNav } from '../stock-nav';
import { StockImportClient } from './stock-import-client';

export default async function StockImportPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.inventory !== false;
    const canManage = session.permissions?.manage_stock ?? false;

    if (!featureEnabled) {
        return <AccessMessage title="Tu plan no incluye Stock" description="Actualizá el plan para habilitar importaciones de inventario." />;
    }

    if (!canManage) {
        return <AccessMessage title="Sin acceso" description="Tu rol no tiene permisos para importar stock." hint="Pedí acceso a un administrador" />;
    }

    return (
        <section className="space-y-6">
            <StockNav />
            <StockImportClient />
        </section>
    );
}
