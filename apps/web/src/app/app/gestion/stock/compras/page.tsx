import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';
import { StockNav } from '../stock-nav';
import { ComprasClient } from './compras-client';

export default async function ComprasPage() {
    const session = await getSession();
    if (!session) redirect('/entrar');

    const canView = session.permissions?.view_purchases ?? false;
    const canManage = session.permissions?.manage_purchases ?? false;

    if (!canView) {
        return (
            <section className="space-y-6">
                <StockNav />
                <AccessMessage
                    title="Sin acceso a Compras"
                    description="Tu rol no puede ver el historial de compras."
                    hint="Pedí acceso a un administrador"
                />
            </section>
        );
    }

    return (
        <section className="space-y-6">
            <StockNav />
            <ComprasClient canManage={canManage} />
        </section>
    );
}
