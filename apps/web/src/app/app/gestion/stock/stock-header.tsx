"use client";

import { AppPageHeader } from '@/components/navigation/app-page-header';
import { ModuleTabs, type ModuleTab } from '@/components/navigation/module-tabs';

const STOCK_TABS: ModuleTab[] = [
    { href: '/app/gestion/stock', label: 'Inventario', exact: true },
    { href: '/app/gestion/stock/compras', label: 'Compras' },
    { href: '/app/gestion/stock/importar', label: 'Importar' },
    { href: '/app/gestion/stock/valorizacion', label: 'Valorización' },
];

export function StockHeader() {
    return (
        <div className="space-y-4">
            <AppPageHeader
                title="Stock"
                description="Gestioná inventario, compras, importaciones y valorización de productos."
            />
            <ModuleTabs
                tabs={STOCK_TABS}
                ariaLabel="Secciones de Stock"
            />
        </div>
    );
}
