"use client";

import { useState } from 'react';

import { useInventorySummary } from '@/features/gestion/hooks';
import { GestionSetupProgressBanner } from '@/features/setup/gestion/components/GestionSetupProgressBanner';
import type { DashboardFeatures, DashboardPermissions } from '../../dashboard-client';
import type { InventorySummaryStats } from '@/features/gestion/types';

import { AlertsBlock } from './alerts-block';
import { ExecutiveHeader } from './executive-header';
import { FinanceAccountsBlock } from './finance-accounts-block';
import { FinanceExpensesBlock } from './finance-expenses-block';
import { KpiStrip } from './kpi-strip';
import { PipelineBlock } from './pipeline-block';
import { PrioritiesList } from './priorities-list';
import { RecentActivityFeed } from './recent-activity-feed';
import { SalesTrendBlock } from './sales-trend-block';
import { SmartActions } from './smart-actions';

type OwnerDashboardProps = {
    initialSummary: InventorySummaryStats | null;
    permissions: DashboardPermissions;
    features: DashboardFeatures;
    planName: string;
};

export function OwnerDashboard({
    initialSummary,
    permissions,
    features,
    planName
}: OwnerDashboardProps) {
    const [helpOpen, setHelpOpen] = useState(false);

    const inventoryQuery = useInventorySummary({ 
        initialData: permissions.canViewStock && features.inventory ? initialSummary : null,
        enabled: permissions.canViewStock && features.inventory,
    });
    
    // Use latest data or initial
    const inventorySummary = inventoryQuery.data ?? initialSummary;

    return (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* 0. Setup Progress Banner (shown until configuration is complete) */}
            <GestionSetupProgressBanner onOpenHelp={() => setHelpOpen(true)} />

            {/* 1. Header Ejecutivo */}
            <ExecutiveHeader 
                inventorySummary={inventorySummary}
                canViewSales={permissions.canViewSales && features.sales}
                canViewCash={permissions.canViewCash && features.cash}
                canViewQuotes={permissions.canViewQuotes && features.quotes}
                canViewStock={permissions.canViewStock && features.inventory}
                helpOpen={helpOpen}
                onHelpOpenChange={setHelpOpen}
            />

            {/* 2. KPI Strip */}
            <KpiStrip
                inventorySummary={inventorySummary}
                canViewSales={permissions.canViewSales && features.sales}
                canViewCash={permissions.canViewCash && features.cash}
                canViewQuotes={permissions.canViewQuotes && features.quotes}
                canViewStock={permissions.canViewStock && features.inventory}
                canViewOrders={permissions.canViewOrders && features.orders}
            />

            <div className="grid grid-cols-1 gap-8 xl:grid-cols-3">
                {/* Left Column: Context & Priorities */}
                <div className="space-y-8 xl:col-span-2">
                    {/* 3. Prioridades */}
                    <PrioritiesList 
                        inventorySummary={inventorySummary}
                        canViewStock={permissions.canViewStock && features.inventory}
                        canViewQuotes={permissions.canViewQuotes && features.quotes}
                        canViewCash={permissions.canViewCash && features.cash}
                        canViewFinance={permissions.canViewFinance && features.treasury}
                    />
                    
                    {/* 4. Acciones Rápidas */}
                    <SmartActions 
                        permissions={permissions}
                        features={features}
                    />

                    {/* 5. Rendimiento Real */}
                    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                        {/* Gráfico de Ventas (Top Productos) */}
                        <div className="md:col-span-2">
                            <SalesTrendBlock 
                                canViewSales={permissions.canViewSales && features.sales}
                            />
                        </div>
                    </div>

                    {/* 6. Actividad Reciente */}
                    <RecentActivityFeed 
                        canViewStock={permissions.canViewStock}
                        inventoryEnabled={features.inventory}
                        canViewSales={permissions.canViewSales}
                        salesEnabled={features.sales}
                        canViewQuotes={permissions.canViewQuotes}
                        quotesEnabled={features.quotes}
                    />
                </div>

                {/* Right Column: Pipeline, Finance, Alerts */}
                <div className="space-y-8 xl:col-span-1">
                    {/* 7. Finanzas y Cuentas (Nuevo Módulo Real) */}
                    <FinanceAccountsBlock 
                        canViewFinance={permissions.canViewFinance && features.treasury}
                    />

                    {/* 7b. Gastos Finanzas — PRO (resumen gastos del mes, fijos pendientes, puntuales sin pagar) */}
                    <FinanceExpensesBlock
                        canViewFinance={permissions.canViewFinance && features.treasury}
                    />

                    {/* 8. Pipeline */}
                    <PipelineBlock 
                        quotesEnabled={permissions.canViewQuotes && features.quotes}
                    />

                    {/* 9. Alertas */}
                    <AlertsBlock 
                        inventorySummary={inventorySummary}
                        canViewStock={permissions.canViewStock && features.inventory}
                        canViewCash={permissions.canViewCash && features.cash}
                        canViewQuotes={permissions.canViewQuotes && features.quotes}
                        canViewOrders={permissions.canViewOrders && features.orders}
                    />
                </div>
            </div>
        </div>
    );
}
