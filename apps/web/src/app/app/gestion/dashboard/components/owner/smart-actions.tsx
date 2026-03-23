"use client";

import { CreditCard, FileText, PackagePlus, ShoppingCart, Store, AlertTriangle, ClipboardList, PackageCheck } from 'lucide-react';
import type { Route } from 'next';
import Link from 'next/link';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCashSummary } from '@/features/cash/hooks';
import { useInventorySummary, usePendingQuotesSummary } from '@/features/gestion/hooks';
import type { DashboardFeatures, DashboardPermissions } from '@/app/app/gestion/dashboard/dashboard-client';

type SmartActionsProps = {
    permissions: DashboardPermissions;
    features: DashboardFeatures;
};

export function SmartActions({ permissions, features }: SmartActionsProps) {
    const cashQuery = useCashSummary(undefined, permissions.canViewCash && features.cash);
    const quotesQuery = usePendingQuotesSummary(permissions.canViewQuotes && features.quotes);
    const inventoryQuery = useInventorySummary({ enabled: permissions.canViewStock && features.inventory });

    const isCashOpen = Boolean(cashQuery.data?.session);
    const pendingQuotes = quotesQuery.data?.count ?? 0;
    const lowStock = inventoryQuery.data?.low_stock ?? 0;

    const actions = [
        {
            id: 'cash-toggle',
            title: isCashOpen ? 'Cerrar caja' : 'Abrir caja',
            icon: isCashOpen ? CreditCard : Store, 
            href: '/app/cash',
            visible: permissions.canViewCash && features.cash,
            priority: isCashOpen ? 10 : 100
        },
        {
            id: 'new-sale',
            title: 'Nueva venta',
            icon: ShoppingCart,
            href: '/app/gestion/ventas/nueva',
            visible: permissions.canCreateSales && features.sales && (isCashOpen || !features.cash),
            priority: 90
        },
        {
            id: 'new-order',
            title: 'Nuevo pedido',
            icon: ClipboardList,
            href: '/app/gestion/ventas/pedidos/nuevo',
            visible: permissions.canViewOrders && features.orders,
            priority: 85
        },
        {
            id: 'new-quote',
            title: 'Crear presupuesto',
            icon: FileText,
            href: '/app/gestion/ventas/presupuestos/nuevo',
            visible: permissions.canCreateQuotes && features.quotes,
            priority: 80
        },
        {
            id: 'pending-quotes',
            title: 'Ver presupuestos',
            icon: FileText,
            href: '/app/gestion/ventas/presupuestos',
            visible: permissions.canViewQuotes && features.quotes && pendingQuotes > 0,
            priority: pendingQuotes > 0 ? 95 : 50
        },
        {
            id: 'new-product',
            title: 'Crear producto',
            icon: PackagePlus,
            href: '/app/gestion/productos',
            visible: permissions.canManageProducts && features.products,
            priority: 70
        },
        {
            id: 'restock',
            title: 'Reponer stock',
            icon: PackageCheck,
            href: '/app/gestion/stock',
            visible: permissions.canManageStock && features.inventory,
            priority: 60
        },
        {
            id: 'stock-alerts',
            title: 'Alertas de stock',
            icon: AlertTriangle,
            href: '/app/gestion/stock?status=low',
            visible: permissions.canViewStock && features.inventory && lowStock > 0,
            priority: lowStock > 0 ? 85 : 30
        },
        {
            id: 'view-sales',
            title: 'Ver ventas',
            icon: ShoppingCart,
            href: '/app/gestion/ventas',
            visible: permissions.canViewSales && features.sales,
            priority: 35
        },
        {
            id: 'finance-access',
            title: 'Ir a Finanzas',
            icon: CreditCard,
            href: '/app/gestion/finanzas/resumen',
            visible: permissions.canViewFinance && features.treasury,
            priority: 20
        },
        {
            id: 'clients-access',
            title: 'Ver clientes',
            icon: Store,
            href: '/app/gestion/clientes',
            visible: permissions.canViewCustomers && features.customers,
            priority: 15
        }
    ];

    const sortedActions = actions
        .filter(a => a.visible)
        .sort((a, b) => b.priority - a.priority);

    return (
        <Card>
            <CardHeader className="pb-3 border-b border-slate-100">
                <CardTitle className="text-base font-semibold text-slate-800">Acciones rápidas</CardTitle>
            </CardHeader>
            <CardContent className="p-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                {sortedActions.slice(0, 8).map((action) => (
                    <Button
                        key={action.id}
                        variant="outline"
                        className="h-auto flex-col gap-2 py-4 border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 hover:text-slate-900 hover:border-slate-300"
                        asChild
                    >
                        <Link href={action.href as Route}>
                            <action.icon className="h-5 w-5" />
                            <span className="text-xs font-semibold">{action.title}</span>
                        </Link>
                    </Button>
                ))}
            </CardContent>
        </Card>
    );
}
