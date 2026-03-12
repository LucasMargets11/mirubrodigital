"use client";

import { DollarSign, TrendingUp, Wallet, ShoppingBag, Package, Banknote } from 'lucide-react';

import { useCashSummary } from '@/features/cash/hooks';
import { usePendingQuotesSummary, useSalesTodaySummary } from '@/features/gestion/hooks';
import type { InventorySummaryStats } from '@/features/gestion/types';
import { formatCurrency, formatNumber } from '@/lib/format';
import { KpiCard } from './kpi-card';

type KpiStripProps = {
    inventorySummary: InventorySummaryStats | null;
    canViewSales: boolean;
    canViewCash: boolean;
    canViewQuotes: boolean;
    canViewStock: boolean;
    canViewFinance: boolean;
};

export function KpiStrip({
    inventorySummary,
    canViewSales,
    canViewCash,
    canViewQuotes,
    canViewStock,
    canViewFinance
}: KpiStripProps) {
    const salesQuery = useSalesTodaySummary(canViewSales);
    const quotesQuery = usePendingQuotesSummary(canViewQuotes);
    const cashQuery = useCashSummary(undefined, canViewCash);

    // const pendingQuotes = quotesQuery.data?.total_pending ?? 0;
    const pendingQuotes = quotesQuery.data?.count ?? 0;
    // const pendingAmount = quotesQuery.data?.total_pending_amount ?? 0;
    const pendingAmount = 0; // Not available in API yet

    const cashStatus = cashQuery.data?.session ? 'Abierta' : 'Cerrada';
    const cashBalance = cashQuery.data?.session?.balance ?? 0;
    const salesToday = salesQuery.data?.total_amount ?? 0;
    const ordersCount = salesQuery.data?.orders_count ?? 0;
    const lowStock = inventorySummary?.low_stock ?? 0;

    return (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {canViewSales && (
                <KpiCard
                    title="Ventas hoy"
                    value={formatCurrency(Number(salesToday))}
                    subValue={`${ordersCount} ops.`}
                    icon={DollarSign}
                    tone="success"
                />
            )}
            
            {canViewQuotes && (
                <KpiCard
                    title="Presupuestos activos"
                    value={formatNumber(pendingQuotes)}
                    subValue={pendingQuotes === 1 ? 'Pendiente' : 'Pendientes'}
                    icon={Banknote}
                    tone={pendingQuotes > 5 ? 'warning' : 'default'}
                />
            )}

            {canViewCash && (
                <KpiCard
                    title="Caja actual"
                    value={cashStatus}
                    subValue={cashStatus === 'Abierta' ? formatCurrency(Number(cashBalance)) : 'Cierre ayer'}
                    icon={Wallet}
                    tone={cashStatus === 'Cerrada' ? 'error' : 'default'}
                />
            )}

            {canViewStock && (
                <KpiCard
                    title="Stock en riesgo"
                    value={formatNumber(lowStock)}
                    subValue="Productos críticos"
                    icon={Package}
                    tone={lowStock > 0 ? 'warning' : 'success'}
                />
            )}
        </div>
    );
}
