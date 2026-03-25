"use client";

import { AppPageHeader } from '@/components/navigation/app-page-header';
import { ModuleTabs, type ModuleTab } from '@/components/navigation/module-tabs';

type ReportesHeaderProps = {
    tabs: { href: string; label: string }[];
};

export function ReportesHeader({ tabs }: ReportesHeaderProps) {
    const moduleTabs: ModuleTab[] = tabs.map((t) => ({
        href: t.href,
        label: t.label,
        exact: t.href === '/app/gestion/reportes',
    }));

    return (
        <div className="space-y-4">
            <AppPageHeader
                title="Reportes"
                description="Monitoreá KPIs, ventas, pagos y cierres de caja en un solo lugar."
            />
            <ModuleTabs
                tabs={moduleTabs}
                ariaLabel="Secciones de Reportes"
            />
        </div>
    );
}
