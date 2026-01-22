import { ReactNode } from 'react';
import { redirect } from 'next/navigation';

import { getSession } from '@/lib/auth';
import type { Session } from '@/lib/auth/types';

import { GestionNav } from './navigation';

const tabConfig = [
    { href: '/app/gestion/dashboard', label: 'Resumen', permission: 'view_dashboard' },
    { href: '/app/gestion/productos', label: 'Productos', permission: 'view_products', feature: 'products' },
    { href: '/app/gestion/stock', label: 'Stock', permission: 'view_stock', feature: 'inventory' },
    { href: '/app/gestion/ventas', label: 'Ventas', permission: 'view_sales', feature: 'sales' },
    { href: '/app/gestion/clientes', label: 'Clientes', permission: 'view_customers', feature: 'customers' },
    { href: '/app/gestion/facturas', label: 'Facturas', permission: 'view_invoices', feature: 'invoices' },
    {
        href: '/app/gestion/reportes',
        label: 'Reportes',
        permission: ['view_reports', 'view_reports_sales', 'view_reports_cash'],
        feature: 'reports',
    },
];

export default async function GestionLayout({ children }: { children: ReactNode }) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const resolvedSession = session as Session;
    const hasGestionService = resolvedSession.services.enabled.includes('gestion');
    const canViewGestion = resolvedSession.permissions?.view_dashboard ?? false;

    if (!hasGestionService || !canViewGestion) {
        redirect('/app/servicios');
    }

    const visibleTabs = tabConfig.filter((tab) => {
        if (tab.feature && resolvedSession.features?.[tab.feature] === false) {
            return false;
        }
        if (tab.permission) {
            const permissions = Array.isArray(tab.permission) ? tab.permission : [tab.permission];
            const hasPermission = permissions.some((permission) => resolvedSession.permissions?.[permission] === true);
            if (!hasPermission) {
                return false;
            }
        }
        return true;
    });

    return (
        <section className="space-y-6">
            <GestionNav tabs={visibleTabs} />
            <div className="space-y-6">{children}</div>
        </section>
    );
}
