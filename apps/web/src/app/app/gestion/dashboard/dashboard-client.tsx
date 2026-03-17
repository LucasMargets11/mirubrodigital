"use client";

import type { InventorySummaryStats } from '@/features/gestion/types';

import { OwnerDashboard } from './components/owner/owner-dashboard';

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
    canViewOrders: boolean;
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
    orders: boolean;
};

type DashboardClientProps = {
    initialSummary: InventorySummaryStats | null;
    permissions: DashboardPermissions;
    features: DashboardFeatures;
    planName: string;
};

export function DashboardClient({ initialSummary, permissions, features, planName }: DashboardClientProps) {
    // For now, we assume everyone landing here gets the new Owner Dashboard as requested.
    // In future, we can switch based on role.
    return (
        <OwnerDashboard 
            initialSummary={initialSummary}
            permissions={permissions}
            features={features}
            planName={planName}
        />
    );
}
