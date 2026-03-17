"use client";

import { Banknote, ClipboardList, DollarSign, Package, PackageX, Wallet } from 'lucide-react';

import { useCashSummary } from '@/features/cash/hooks';
import { usePendingOrdersSummary, usePendingQuotesSummary, useSalesTodaySummary } from '@/features/gestion/hooks';
import type { InventorySummaryStats } from '@/features/gestion/types';
import { formatCurrency, formatNumber } from '@/lib/format';
import { KpiCard } from './kpi-card';

type KpiStripProps = {
    inventorySummary: InventorySummaryStats | null;
    canViewSales: boolean;
    canViewCash: boolean;
    canViewQuotes: boolean;
    canViewStock: boolean;
    canViewOrders: boolean;
};

type KpiConfig = {
    key: string;
    title: string;
    value: string;
    subValue?: string;
    icon: typeof DollarSign;
    tone: 'default' | 'success' | 'warning' | 'error';
    href?: string;
    visible: boolean;
    loading: boolean;
};

export function KpiStrip({
    inventorySummary,
    canViewSales,
    canViewCash,
    canViewQuotes,
    canViewStock,
    canViewOrders,
}: KpiStripProps) {
    const salesQuery = useSalesTodaySummary(canViewSales);
    const quotesQuery = usePendingQuotesSummary(canViewQuotes);
    const cashQuery = useCashSummary(undefined, canViewCash);
    const ordersQuery = usePendingOrdersSummary(canViewOrders);

    const pendingQuotes = quotesQuery.data?.count ?? 0;
    const cashStatus = cashQuery.data?.session ? 'Abierta' : 'Cerrada';
    const cashBalance = cashQuery.data?.session?.totals?.cash_expected_total ?? '0';
    const salesToday = salesQuery.data?.total_amount ?? 0;
    const ordersCount = salesQuery.data?.orders_count ?? 0;
    const lowStock = inventorySummary?.low_stock ?? 0;
    const outOfStock = inventorySummary?.out_of_stock ?? 0;
    const pendingOrders = ordersQuery.data?.count ?? 0;

    const kpis: KpiConfig[] = [
        {
            key: 'sales-today',
            title: 'Ventas hoy',
            value: formatCurrency(Number(salesToday)),
            subValue: `${ordersCount} ops.`,
            icon: DollarSign,
            tone: 'success',
            href: '/app/gestion/ventas',
            visible: canViewSales,
            loading: salesQuery.isLoading,
        },
        {
            key: 'pending-quotes',
            title: 'Presupuestos activos',
            value: formatNumber(pendingQuotes),
            subValue: pendingQuotes === 1 ? 'Pendiente' : 'Pendientes',
            icon: Banknote,
            tone: pendingQuotes > 5 ? 'warning' : 'default',
            href: '/app/gestion/ventas/presupuestos',
            visible: canViewQuotes,
            loading: quotesQuery.isLoading,
        },
        {
            key: 'cash',
            title: 'Caja actual',
            value: cashStatus,
            subValue: cashStatus === 'Abierta' ? formatCurrency(Number(cashBalance)) : 'Sin sesión activa',
            icon: Wallet,
            tone: cashStatus === 'Cerrada' ? 'error' : 'default',
            href: '/app/cash',
            visible: canViewCash,
            loading: cashQuery.isLoading,
        },
        {
            key: 'pending-orders',
            title: 'Pedidos pendientes',
            value: formatNumber(pendingOrders),
            subValue: pendingOrders === 1 ? 'En proceso' : 'En proceso',
            icon: ClipboardList,
            tone: pendingOrders > 0 ? 'warning' : 'default',
            href: '/app/gestion/ventas/pedidos',
            visible: canViewOrders,
            loading: ordersQuery.isLoading,
        },
        {
            key: 'out-of-stock',
            title: 'Sin stock',
            value: formatNumber(outOfStock),
            subValue: outOfStock === 1 ? 'Producto agotado' : 'Productos agotados',
            icon: PackageX,
            tone: outOfStock > 0 ? 'error' : 'success',
            href: '/app/gestion/stock?status=out',
            visible: canViewStock,
            loading: false,
        },
        {
            key: 'low-stock',
            title: 'Stock bajo',
            value: formatNumber(lowStock),
            subValue: lowStock === 1 ? 'Producto crítico' : 'Productos críticos',
            icon: Package,
            tone: lowStock > 0 ? 'warning' : 'success',
            href: '/app/gestion/stock?status=low',
            visible: canViewStock,
            loading: false,
        },
    ];

    const visibleKpis = kpis.filter((k) => k.visible);

    if (visibleKpis.length === 0) return null;

    return (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-6">
            {visibleKpis.map((kpi) => (
                <KpiCard
                    key={kpi.key}
                    title={kpi.title}
                    value={kpi.value}
                    subValue={kpi.subValue}
                    icon={kpi.icon}
                    tone={kpi.tone}
                    href={kpi.href}
                    loading={kpi.loading}
                />
            ))}
        </div>
    );
}
