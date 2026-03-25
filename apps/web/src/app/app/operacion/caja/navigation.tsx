"use client";

import { AppPageHeader } from '@/components/navigation/app-page-header';
import { ModuleTabs, type ModuleTab } from '@/components/navigation/module-tabs';

type Tab = {
    href: string;
    label: string;
};

type OperacionCajaNavProps = {
    tabs: Tab[];
};

export function OperacionCajaNav({ tabs }: OperacionCajaNavProps) {
    if (tabs.length === 0) {
        return null;
    }

    const moduleTabs: ModuleTab[] = tabs.map((t) => ({
        href: t.href,
        label: t.label,
        exact: t.href === '/app/operacion/caja',
    }));

    return (
        <div className="space-y-4">
            <AppPageHeader
                title="Caja"
                description="Gestioná la operación diaria de caja, movimientos y cierres."
            />
            <ModuleTabs
                tabs={moduleTabs}
                ariaLabel="Secciones de Caja"
            />
        </div>
    );
}
