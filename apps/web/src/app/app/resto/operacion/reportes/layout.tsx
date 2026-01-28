import type { ReactNode } from 'react';
import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';
import type { Session } from '@/lib/auth/types';
import { ReportsSubnav } from '@/modules/reports/components/subnav';

const tabs = [
    { href: '/app/resto/operacion/reportes', label: 'Dashboard' },
    { href: '/app/resto/operacion/reportes/caja', label: 'Caja' },
];

type ReportsLayoutProps = {
    children: ReactNode;
};

export default async function RestauranteOperationReportsLayout({ children }: ReportsLayoutProps) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const resolved = session as Session;
    if (resolved.current.service !== 'restaurante') {
        redirect('/app/servicios');
    }

    const featureEnabled = resolved.features?.resto_reports !== false;
    const canViewReports = resolved.permissions?.view_restaurant_reports === true;

    if (!featureEnabled || !canViewReports) {
        return (
            <AccessMessage
                title="Reportes no disponibles"
                description="Tu plan o rol actual no permite ver los reportes de operación del Restaurante Inteligente."
                hint="Contactá a un administrador para habilitarlo"
            />
        );
    }

    return (
        <section className="space-y-6">
            <header className="space-y-4 rounded-3xl border border-slate-200 bg-white/80 p-6 shadow-sm">
                <div>
                    <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Operación restaurante</p>
                    <div className="mt-2 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                        <div>
                            <h1 className="text-3xl font-semibold text-slate-900">Reportes</h1>
                            <p className="text-sm text-slate-500">Seguimiento de ventas, cajas y productos clave del servicio Restaurante Inteligente.</p>
                        </div>
                        <ReportsSubnav tabs={tabs} />
                    </div>
                </div>
            </header>
            {children}
        </section>
    );
}
