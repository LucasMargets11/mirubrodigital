import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';

import { StockNav } from '../stock-nav';
import { StockValuationClient } from '../valuation-client';

export default async function StockValuationPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const inventoryEnabled = session.features?.inventory !== false;
    const productsEnabled = session.features?.products !== false;
    const canViewStock = session.permissions?.view_stock ?? false;
    const canViewCost = session.permissions?.manage_products ?? false;

    if (!inventoryEnabled || !productsEnabled) {
        return (
            <AccessMessage
                title="Tu plan no incluye Valorización"
                description="Necesitás tener Productos e Inventario habilitados para ver la proyección de stock."
            />
        );
    }

    if (!canViewStock) {
        return <AccessMessage title="Sin acceso" description="Tu rol no puede ver el inventario." hint="Pedí acceso a un administrador" />;
    }

    return (
        <section className="space-y-6">
            <StockNav />
            <StockValuationClient canViewCost={canViewCost} />
        </section>
    );
}
