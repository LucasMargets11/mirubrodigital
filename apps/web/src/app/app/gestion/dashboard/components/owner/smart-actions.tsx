"use client";

import { CreditCard, FileText, PackagePlus, ShoppingCart, Store, AlertTriangle } from 'lucide-react';
import type { Route } from 'next';
import Link from 'next/link';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCashSummary } from '@/features/cash/hooks';
import { useInventorySummary, usePendingQuotesSummary } from '@/features/gestion/hooks';
import { cn } from '@/lib/utils';
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
            variant: isCashOpen ? 'outline' : 'default', // Primary if closed
            priority: isCashOpen ? 10 : 100 // High priority if closed
        },
        {
            id: 'new-sale',
            title: 'Nueva venta',
            icon: ShoppingCart,
            href: '/app/gestion/ventas/nueva',
            visible: permissions.canCreateSales && features.sales && isCashOpen,
            variant: 'default',
            priority: 90
        },
        {
            id: 'new-quote',
            title: 'Crear presupuesto',
            icon: FileText,
            href: '/app/gestion/ventas/presupuestos/nuevo',
            visible: permissions.canCreateQuotes && features.quotes,
            variant: 'outline',
            priority: 80
        },
        {
            id: 'pending-quotes',
            title: 'Ver presupuestos',
            icon: FileText,
            href: '/app/gestion/ventas/presupuestos',
            visible: permissions.canViewQuotes && features.quotes && pendingQuotes > 0,
            variant: 'outline', // High priority if pending
            priority: pendingQuotes > 0 ? 95 : 50
        },
        {
            id: 'new-product',
            title: 'Crear producto',
            icon: PackagePlus,
            href: '/app/gestion/productos',
            visible: permissions.canManageProducts && features.products,
            variant: 'ghost',
            priority: 40
        },
        {
            id: 'stock-alerts',
            title: 'Alertas de stock',
            icon: AlertTriangle,
            href: '/app/gestion/stock?status=low',
            visible: permissions.canViewStock && features.inventory && lowStock > 0,
            variant: 'outline',
            priority: lowStock > 0 ? 85 : 30
        },
        {
            id: 'finance-access',
            title: 'Ir a Finanzas',
            icon: CreditCard,
            href: '/app/gestion/finanzas/resumen',
            visible: permissions.canViewFinance && features.treasury,
            variant: 'ghost',
            priority: 20
        },
        {
            id: 'clients-access',
            title: 'Ver clientes',
            icon: Store,
            href: '/app/gestion/clientes',
            visible: permissions.canViewCustomers && features.customers,
            variant: 'ghost',
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
                        variant={action.variant as 'default' | 'outline' | 'ghost'}
                        className={cn(
                            "h-auto flex-col gap-2 py-4 shadow-sm",
                            action.variant === 'ghost' && "bg-slate-50 hover:bg-slate-100"
                        )}
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
