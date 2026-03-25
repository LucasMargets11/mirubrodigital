import { ReactNode } from 'react';
import { redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { getSession } from '@/lib/auth';
import type { Session } from '@/lib/auth/types';

import { ReportesHeader } from './reportes-header';

type ReportsLayoutProps = {
    children: ReactNode;
};

const subTabs = [
    { href: '/app/gestion/reportes', label: 'Resumen', permission: 'view_dashboard' },
    { href: '/app/gestion/reportes/ventas', label: 'Ventas', permission: 'view_reports_sales', feature: 'reports' },
    { href: '/app/gestion/reportes/pagos', label: 'Pagos', permission: 'view_reports_sales', feature: 'reports' },
    { href: '/app/gestion/reportes/caja', label: 'Caja', permission: 'view_reports_cash', feature: 'reports' },
    { href: '/app/gestion/reportes/productos', label: 'Productos', permission: 'view_reports_products', feature: 'reports' },
];

export default async function ReportsLayout({ children }: ReportsLayoutProps) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const resolved = session as Session;
    const permissions = resolved.permissions ?? {};
    const features = resolved.features ?? {};
    
    const visibleTabs = subTabs.filter((tab) => {
        if (!permissions?.[tab.permission]) {
            return false;
        }
        if (tab.feature && features?.[tab.feature] === false) {
            return false;
        }
        return true;
    });

    if (visibleTabs.length === 0) {
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
            <ReportesHeader tabs={visibleTabs} />
            {children}
        </section>
    );
}
