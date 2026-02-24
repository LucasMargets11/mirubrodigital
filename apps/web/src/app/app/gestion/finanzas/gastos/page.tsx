import { Suspense } from 'react';
import { redirect } from 'next/navigation';
import { AccessMessage } from '@/components/app/access-message';
import { GastosClient } from './gastos-client';
import { getSession } from '@/lib/auth';
import { Loader2 } from 'lucide-react';

export default async function FinanzasGastosPage() {
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

    return (
        <Suspense fallback={<div className="flex justify-center p-12"><Loader2 className="h-8 w-8 animate-spin text-slate-400" /></div>}>
            <GastosClient canManage={canManage} />
        </Suspense>
    );
}
