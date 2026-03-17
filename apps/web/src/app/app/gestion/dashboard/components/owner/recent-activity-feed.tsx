"use client";

import { useMemo } from 'react';
import type { Route } from 'next';
import Link from 'next/link';
import { formatDistanceToNow } from 'date-fns';
import { es } from 'date-fns/locale';
import { ArrowLeftRight, FileText, ShoppingCart, Loader2 } from 'lucide-react';

import { useRecentInventoryMovements, useRecentQuotes, useRecentSales } from '@/features/gestion/hooks';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { formatCurrency, formatNumber } from '@/lib/format';

type RecentActivityFeedProps = {
    canViewStock: boolean;
    inventoryEnabled: boolean;
    canViewSales: boolean;
    salesEnabled: boolean;
    canViewQuotes: boolean;
    quotesEnabled: boolean;
};

type ActivityEvent = {
    id: string;
    kind: 'sale' | 'movement' | 'quote';
    title: string;
    description: string;
    timestamp: Date; // Keep as Date for sorting, format later
    href?: string;
    icon: any;
    amountLabel?: string;
    tone: 'success' | 'warning' | 'info';
};

export function RecentActivityFeed({ 
    canViewStock, 
    inventoryEnabled, 
    canViewSales, 
    salesEnabled, 
    canViewQuotes, 
    quotesEnabled 
}: RecentActivityFeedProps) {
    const inventoryQuery = useRecentInventoryMovements(5, canViewStock && inventoryEnabled);
    const salesQuery = useRecentSales(5, canViewSales && salesEnabled);
    const quotesQuery = useRecentQuotes(5, canViewQuotes && quotesEnabled);

    const isLoading = inventoryQuery.isLoading || salesQuery.isLoading || quotesQuery.isLoading;

    const activities = useMemo(() => {
        const events: ActivityEvent[] = [];

        if (salesEnabled && salesQuery.data) {
            salesQuery.data.forEach((sale) => {
                events.push({
                    id: `sale-${sale.id}`,
                    kind: 'sale',
                    title: `Venta #${sale.number}`,
                    description: sale.customer_name || 'Cliente Ocasional',
                    timestamp: new Date(sale.created_at),
                    href: `/app/gestion/ventas/${sale.id}`,
                    icon: ShoppingCart,
                    amountLabel: formatCurrency(Number(sale.total)),
                    tone: 'success',
                });
            });
        }

        if (inventoryEnabled && inventoryQuery.data) {
            inventoryQuery.data.forEach((movement) => {
                const isOut = movement.movement_type === 'OUT' || movement.movement_type === 'WASTE';
                events.push({
                    id: `mov-${movement.id}`,
                    kind: 'movement',
                    title: isOut ? 'Salida de stock' : 'Entrada de stock',
                    description: `${formatNumber(movement.quantity)} x ${movement.product.name}`,
                    timestamp: new Date(movement.created_at),
                    icon: ArrowLeftRight,
                    tone: isOut ? 'warning' : 'info',
                });
            });
        }

        if (quotesEnabled && quotesQuery.data) {
            quotesQuery.data.forEach((quote) => {
                events.push({
                    id: `quote-${quote.id}`,
                    kind: 'quote',
                    title: `Presupuesto #${quote.number}`,
                    description: quote.customer_name || 'Prospecto',
                    timestamp: new Date(quote.created_at),
                    href: `/app/gestion/presupuestos/${quote.id}`,
                    icon: FileText,
                    amountLabel: formatCurrency(Number(quote.total)),
                    tone: 'info',
                });
            });
        }

        return events.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime()).slice(0, 5);
    }, [
        salesEnabled, salesQuery.data,
        inventoryEnabled, inventoryQuery.data,
        quotesEnabled, quotesQuery.data
    ]);

    if (isLoading) {
        return (
            <Card className="h-full min-h-[300px] flex items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-slate-300" />
            </Card>
        );
    }

    if (activities.length === 0) {
        return (
            <Card className="h-full min-h-[200px] flex flex-col items-center justify-center p-8 text-center border-dashed">
                <div className="rounded-full bg-slate-50 p-4 mb-3">
                    <FileText className="h-6 w-6 text-slate-400" />
                </div>
                <h3 className="font-medium text-slate-900">Sin actividad reciente</h3>
                <p className="text-sm text-slate-500 mt-1">
                    No hubo movimientos, ventas ni presupuestos en las últimas horas.
                </p>
            </Card>
        );
    }

    return (
        <Card className="col-span-1 lg:col-span-1 border-slate-100/50">
            <CardHeader className="pb-3 border-b border-slate-100">
                <CardTitle className="text-base font-semibold text-slate-800">
                    Actividad reciente
                </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
                <div className="divide-y divide-slate-100">
                    {activities.map((item) => (
                        <div key={item.id} className="group relative flex items-center gap-4 p-4 hover:bg-slate-50/50 transition-colors">
                            <div className={cn(
                                "flex h-10 w-10 shrink-0 items-center justify-center rounded-full border",
                                item.tone === 'success' && "bg-emerald-50 border-emerald-100 text-emerald-600",
                                item.tone === 'warning' && "bg-amber-50 border-amber-100 text-amber-600",
                                item.tone === 'info' && "bg-blue-50 border-blue-100 text-blue-600",
                            )}>
                                <item.icon className="h-5 w-5" />
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center justify-between mb-0.5">
                                    <p className="text-sm font-medium text-slate-900 truncate">
                                        {item.title}
                                    </p>
                                    <span className="text-xs text-slate-400 shrink-0 ml-2">
                                        {formatDistanceToNow(item.timestamp, { addSuffix: true, locale: es })}
                                    </span>
                                </div>
                                <div className="flex items-center justify-between">
                                    <p className="text-sm text-slate-500 truncate pr-2">
                                        {item.description}
                                    </p>
                                    {item.amountLabel && (
                                        <span className="text-sm font-semibold text-slate-700">
                                            {item.amountLabel}
                                        </span>
                                    )}
                                </div>
                            </div>
                            {item.href && (
                                <Link href={item.href as Route} className="absolute inset-0" aria-label={`Ver detalle de ${item.title}`} />
                            )}
                        </div>
                    ))}
                </div>
            </CardContent>
        </Card>
    );
}
