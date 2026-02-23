import { redirect } from 'next/navigation';
import { AccessMessage } from '@/components/app/access-message';
import { DashboardClient } from './dashboard-client';
import { getSession } from '@/lib/auth';

export default async function FinanzasResumenPage() {
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

    return <DashboardClient canManage={canManage} />;
}
