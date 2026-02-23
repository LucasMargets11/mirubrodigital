import { redirect } from 'next/navigation';
import { AccessMessage } from '@/components/app/access-message';
import { TransactionsClient } from './transactions-client';
import { getSession } from '@/lib/auth';
import { listAccounts, listCategories } from '@/lib/api/treasury';

export default async function FinanzasMovimientosPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.treasury !== false;
    const canView = session.permissions?.view_finance ?? false;
    const canManage = session.permissions?.manage_finance ?? false;

    if (!featureEnabled) {
        return <AccessMessage title="Tu plan no incluye Finanzas" description="Actualizá a PRO para acceder al módulo de Tesorería y Finanzas." />;
    }

    if (!canView) {
        return <AccessMessage title="Sin acceso" description="Tu rol no puede ver finanzas." hint="Pedí acceso a un administrador" />;
    }

    // Prefetch for filters
    // We could do this client side with react-query too, but layout pattern suggests client usually.
    // I'll stick to client fetching in the Client Component for consistency with AccountsClient.
    
    return <TransactionsClient canManage={canManage} />;
}
