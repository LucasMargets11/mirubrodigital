"use client";

import type { InventorySummaryStats } from '@/features/gestion/types';

import { HealthCards } from './components/health-cards';
import { QuickActions } from './components/quick-actions';
import { RecentActivity } from './components/recent-activity';
import { StockAlerts } from './components/stock-alerts';
import { TopProducts } from './components/top-products';

export type DashboardPermissions = {
    canManageProducts: boolean;
    canManageStock: boolean;
    canCreateSales: boolean;
    canViewStock: boolean;
    canViewSales: boolean;
    canViewCash: boolean;
    canViewQuotes: boolean;
    canCreateQuotes: boolean;
    canViewCustomers: boolean;
    canViewInvoices: boolean;
    canViewFinance: boolean;
};

export type DashboardFeatures = {
    products: boolean;
    inventory: boolean;
    sales: boolean;
    cash: boolean;
    quotes: boolean;
    customers: boolean;
    invoices: boolean;
    treasury: boolean;
};

type DashboardClientProps = {
    initialSummary: InventorySummaryStats | null;
    permissions: DashboardPermissions;
    features: DashboardFeatures;
    planName: string;
};

export function DashboardClient({ initialSummary, permissions, features, planName }: DashboardClientProps) {
    return (
        <div className="space-y-6">
            <HealthCards
                initialSummary={initialSummary}
                canViewStock={permissions.canViewStock}
                inventoryEnabled={features.inventory}
                canViewSales={permissions.canViewSales}
                salesEnabled={features.sales}
                canViewCash={permissions.canViewCash}
                cashEnabled={features.cash}
                canViewQuotes={permissions.canViewQuotes}
                quotesEnabled={features.quotes}
            />
            <QuickActions permissions={permissions} features={features} />
            <div className="grid gap-6 xl:grid-cols-2">
                <div className="space-y-6">
                    <StockAlerts canView={permissions.canViewStock} inventoryEnabled={features.inventory} />
                    <TopProducts canViewSales={permissions.canViewSales} salesEnabled={features.sales} />
                </div>
                <div className="space-y-6">
                    <RecentActivity
                        canViewStock={permissions.canViewStock}
                        inventoryEnabled={features.inventory}
                        canViewSales={permissions.canViewSales}
                        salesEnabled={features.sales}
                        canViewQuotes={permissions.canViewQuotes}
                        quotesEnabled={features.quotes}
                    />
                </div>
            </div>
        </div>
    );
}
