import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';
import { SalesClient } from '../sales-client';
import { QuotesClient } from '../quotes-client';

export default async function PresupuestosPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const salesFeature = session.features?.sales !== false;
    const quotesFeature = session.features?.quotes !== false;
    const canView = session.permissions?.view_quotes ?? false;
    const canCreate = session.permissions?.create_quotes ?? false;
    const canSend = session.permissions?.send_quotes ?? false;
    
    // Props para el header
    const canViewSales = session.permissions?.view_sales ?? false;
    const canCreateSales = session.permissions?.create_sales ?? false;

    if (!salesFeature) {
        return <AccessMessage title="Tu plan no incluye Ventas" description="Actualizá tu plan para habilitar el módulo de ventas." />;
    }

    if (!quotesFeature) {
        return <AccessMessage title="Tu plan no incluye Presupuestos" description="Actualizá a PRO para usar presupuestos y cotizaciones." />;
    }

    if (!canView) {
        return <AccessMessage title="Sin acceso" description="Tu rol no puede ver los presupuestos." hint="Pedí acceso a un administrador" />;
    }

    return (
        <section className="space-y-4">
            <SalesClient 
                canCreate={canCreateSales} 
                canViewQuotes={canView} 
                canCreateQuotes={canCreate} 
            />
            <QuotesClient canCreate={canCreate} canSend={canSend} />
        </section>
    );
}
