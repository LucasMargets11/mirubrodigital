"use client";

import { AppPageHeader } from '@/components/navigation/app-page-header';
import { ModuleTabs, type ModuleTab } from '@/components/navigation/module-tabs';

const FINANCE_TABS: ModuleTab[] = [
    { href: '/app/gestion/finanzas/resumen', label: 'Resumen' },
    { href: '/app/gestion/finanzas/cuentas', label: 'Cuentas' },
    { href: '/app/gestion/finanzas/movimientos', label: 'Movimientos' },
    { href: '/app/gestion/finanzas/gastos', label: 'Gastos' },
    { href: '/app/gestion/finanzas/sueldos', label: 'Sueldos' },
    { href: '/app/gestion/finanzas/reportes', label: 'Reportes financieros' },
    { href: '/app/gestion/finanzas/configuracion', label: 'Ajustes' },
];

export function FinanzasNav() {
    return (
        <div className="space-y-4">
            <AppPageHeader
                title="Finanzas"
                description="Control de caja, bancos y gastos. Registro interno, no conectado a bancos."
            />
            <ModuleTabs
                tabs={FINANCE_TABS}
                ariaLabel="Secciones de Finanzas"
            />
        </div>
    );
}
