import { redirect } from 'next/navigation';

import { serverApiFetch } from '@/lib/api/server';
import { getSession } from '@/lib/auth';
import type { InventorySummaryStats } from '@/features/gestion/types';

import { DashboardClient } from './dashboard-client';

export default async function GestionDashboardPage() {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const canViewStock = session.permissions?.view_stock ?? false;
    const canViewSales = session.permissions?.view_sales ?? false;
    const canViewCash = session.permissions?.view_cash ?? false;
    const canViewQuotes = session.permissions?.view_quotes ?? false;
    const canCreateQuotes = session.permissions?.create_quotes ?? false;
    const canViewCustomers = session.permissions?.view_customers ?? false;
    const canViewInvoices = session.permissions?.view_invoices ?? false;
    const canViewFinance = session.permissions?.view_finance ?? false;

    const inventoryEnabled = session.features?.inventory !== false;
    const salesEnabled = session.features?.sales !== false;
    const cashEnabled = session.features?.cash !== false;
    const quotesEnabled = session.features?.quotes !== false;
    const customersEnabled = session.features?.customers !== false;
    const invoicesEnabled = session.features?.invoices !== false;
    const treasuryEnabled = session.features?.treasury !== false;

    let summary: InventorySummaryStats | null = null;
    if (canViewStock && inventoryEnabled) {
        try {
            summary = await serverApiFetch<InventorySummaryStats>('/api/v1/inventory/summary/');
        } catch (error) {
            summary = null;
        }
    }

    return (
        <DashboardClient
            initialSummary={summary}
            permissions={{
                canManageProducts: session.permissions?.manage_products ?? false,
                canManageStock: session.permissions?.manage_stock ?? false,
                canCreateSales: session.permissions?.create_sales ?? false,
                canViewStock,
                canViewSales,
                canViewCash,
                canViewQuotes,
                canCreateQuotes,
                canViewCustomers,
                canViewInvoices,
                canViewFinance,
            }}
            features={{
                products: session.features?.products !== false,
                inventory: inventoryEnabled,
                sales: salesEnabled,
                cash: cashEnabled,
                quotes: quotesEnabled,
                customers: customersEnabled,
                invoices: invoicesEnabled,
                treasury: treasuryEnabled,
            }}
            planName={session.subscription.plan}
        />
    );
}
