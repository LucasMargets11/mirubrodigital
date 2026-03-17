"use client";

import type { Route } from 'next';
import Link from 'next/link';
import {
    AlertTriangle,
    ArrowRight,
    Box,
    CalendarX2,
    CheckCircle2,
    CircleAlert,
    ClipboardList,
    PackageX,
    type LucideIcon,
} from 'lucide-react';

import type { InventorySummaryStats } from '@/features/gestion/types';
import { usePendingOrdersSummary, usePendingQuotesSummary } from '@/features/gestion/hooks';
import { useCashSummary } from '@/features/cash/hooks';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

type AlertSeverity = 'critical' | 'urgent' | 'important';

type AlertItem = {
    id: string;
    title: string;
    count: number;
    description: string;
    severity: AlertSeverity;
    href: string;
    icon: LucideIcon;
};

type AlertsBlockProps = {
    inventorySummary: InventorySummaryStats | null;
    canViewStock: boolean;
    canViewCash: boolean;
    canViewQuotes: boolean;
    canViewOrders: boolean;
};

const severityStyles: Record<AlertSeverity, { row: string; badge: string; icon: string }> = {
    critical: {
        row: 'hover:bg-red-50/50',
        badge: 'bg-red-100 text-red-700',
        icon: 'text-red-500',
    },
    urgent: {
        row: 'hover:bg-amber-50/50',
        badge: 'bg-amber-100 text-amber-700',
        icon: 'text-amber-500',
    },
    important: {
        row: 'hover:bg-blue-50/50',
        badge: 'bg-blue-100 text-blue-700',
        icon: 'text-blue-500',
    },
};

export function AlertsBlock({
    inventorySummary,
    canViewStock,
    canViewCash,
    canViewQuotes,
    canViewOrders,
}: AlertsBlockProps) {
    const cashQuery = useCashSummary(undefined, canViewCash);
    const quotesQuery = usePendingQuotesSummary(canViewQuotes);
    const ordersQuery = usePendingOrdersSummary(canViewOrders);

    const lowStock = inventorySummary?.low_stock ?? 0;
    const outOfStock = inventorySummary?.out_of_stock ?? 0;
    const isCashClosed = canViewCash && !cashQuery.data?.session;
    const pendingQuotes = quotesQuery.data?.count ?? 0;
    const pendingOrders = ordersQuery.data?.count ?? 0;

    const alerts: AlertItem[] = [];

    if (canViewCash && isCashClosed && !cashQuery.isLoading) {
        alerts.push({
            id: 'cash-closed',
            title: 'Caja cerrada',
            count: 1,
            description: 'Abrí la caja para comenzar a operar',
            severity: 'critical',
            href: '/app/cash',
            icon: CircleAlert,
        });
    }

    if (canViewStock && outOfStock > 0) {
        alerts.push({
            id: 'out-of-stock',
            title: 'Sin stock',
            count: outOfStock,
            description: outOfStock === 1 ? 'producto agotado' : 'productos agotados',
            severity: 'urgent',
            href: '/app/gestion/stock?status=out',
            icon: PackageX,
        });
    }

    if (canViewStock && lowStock > 0) {
        alerts.push({
            id: 'low-stock',
            title: 'Stock bajo',
            count: lowStock,
            description: lowStock === 1 ? 'producto en nivel crítico' : 'productos en nivel crítico',
            severity: 'important',
            href: '/app/gestion/stock?status=low',
            icon: Box,
        });
    }

    if (canViewQuotes && pendingQuotes > 0 && !quotesQuery.isLoading) {
        alerts.push({
            id: 'pending-quotes',
            title: 'Presupuestos pendientes',
            count: pendingQuotes,
            description: pendingQuotes === 1 ? 'presupuesto sin responder' : 'presupuestos sin responder',
            severity: 'important',
            href: '/app/gestion/ventas/presupuestos',
            icon: CalendarX2,
        });
    }

    if (canViewOrders && pendingOrders > 0 && !ordersQuery.isLoading) {
        alerts.push({
            id: 'pending-orders',
            title: 'Pedidos en proceso',
            count: pendingOrders,
            description: pendingOrders === 1 ? 'pedido requiere atención' : 'pedidos requieren atención',
            severity: 'important',
            href: '/app/gestion/ventas/pedidos',
            icon: ClipboardList,
        });
    }

    if (alerts.length === 0) {
        return (
            <Card className="border-slate-100 bg-slate-50/50">
                <CardContent className="flex flex-col items-center justify-center p-6 text-center">
                    <div className="rounded-full bg-emerald-100 p-2 mb-2">
                        <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                    </div>
                    <p className="font-medium text-slate-900">Sin alertas activas</p>
                    <p className="text-xs text-slate-500 mt-0.5">Todo en orden por ahora.</p>
                </CardContent>
            </Card>
        );
    }

    const hasCritical = alerts.some((a) => a.severity === 'critical');
    const hasUrgent = alerts.some((a) => a.severity === 'urgent');
    const borderColor = hasCritical ? 'border-red-200' : hasUrgent ? 'border-amber-200' : 'border-blue-200';

    return (
        <Card className={cn("overflow-hidden", borderColor)}>
            <CardHeader className="pb-2 border-b border-slate-100">
                <CardTitle className="text-base font-semibold text-slate-900 flex items-center gap-2">
                    <AlertTriangle className={cn(
                        "h-5 w-5",
                        hasCritical ? 'text-red-500' : hasUrgent ? 'text-amber-500' : 'text-blue-500',
                    )} />
                    Alertas
                    <span className={cn(
                        "ml-auto text-xs font-medium px-2 py-0.5 rounded-full",
                        hasCritical ? 'bg-red-100 text-red-700' : hasUrgent ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700',
                    )}>
                        {alerts.length}
                    </span>
                </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
                <div className="divide-y divide-slate-100">
                    {alerts.map((alert) => {
                        const style = severityStyles[alert.severity];
                        const Icon = alert.icon;
                        return (
                            <Link
                                key={alert.id}
                                href={alert.href as Route}
                                className={cn(
                                    "flex items-center gap-3 px-4 py-3 transition-colors group focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-slate-300",
                                    style.row,
                                )}
                            >
                                <Icon className={cn("h-4 w-4 shrink-0", style.icon)} />
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-medium text-slate-900 truncate">
                                        {alert.title}
                                    </p>
                                    <p className="text-xs text-slate-500 truncate">
                                        {alert.count} {alert.description}
                                    </p>
                                </div>
                                <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full shrink-0", style.badge)}>
                                    {alert.count}
                                </span>
                                <ArrowRight className="h-3.5 w-3.5 text-slate-300 shrink-0 transition-transform group-hover:translate-x-0.5" />
                            </Link>
                        );
                    })}
                </div>
            </CardContent>
        </Card>
    );
}
