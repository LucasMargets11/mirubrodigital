import { ReactNode } from 'react';
import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';
import type { Session } from '@/lib/auth/types';

import { ReportsSubnav } from './components/reports-subnav';

type ReportsLayoutProps = {
    children: ReactNode;
};

const subTabs = [
    { href: '/app/gestion/reportes', label: 'Resumen', permission: 'view_reports' },
    { href: '/app/gestion/reportes/ventas', label: 'Ventas', permission: 'view_reports_sales' },
    { href: '/app/gestion/reportes/pagos', label: 'Pagos', permission: 'view_reports_sales' },
    { href: '/app/gestion/reportes/caja', label: 'Caja', permission: 'view_reports_cash' },
    { href: '/app/gestion/reportes/productos', label: 'Productos', permission: 'view_reports_products' },
];

export default async function ReportsLayout({ children }: ReportsLayoutProps) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const resolved = session as Session;
    const featureEnabled = resolved.features?.reports !== false;
    const permissions = resolved.permissions ?? {};
    const visibleTabs = subTabs.filter((tab) => permissions?.[tab.permission] === true);

    if (!featureEnabled || visibleTabs.length === 0) {
        return (
            <AccessMessage
                title="Sin acceso a Reportes"
                description="Tu plan o rol actual no permite ver el módulo de reportes."
                hint="Contactá a un administrador para habilitarlo"
            />
        );
    }

    return (
        <section className="space-y-6">
            <header className="space-y-4 rounded-3xl border border-slate-200 bg-white/80 p-6 shadow-sm">
                <div>
                    <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Gestión Comercial</p>
                    <div className="mt-2 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                        <div>
                            <h1 className="text-3xl font-semibold text-slate-900">Reportes</h1>
                            <p className="text-sm text-slate-500">Monitoreá KPIs, ventas, pagos y cierres de caja en un solo lugar.</p>
                        </div>
                        <ReportsSubnav tabs={visibleTabs} />
                    </div>
                </div>
            </header>
            {children}
        </section>
    );
}
