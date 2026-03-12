"use client";

import { AlertTriangle, ArrowRight, Box, CheckCircle, Clock } from 'lucide-react';
import Link from 'next/link';

import { useCashSummary } from '@/features/cash/hooks';
import type { InventorySummaryStats } from '@/features/gestion/types';
import { usePendingQuotesSummary } from '@/features/gestion/hooks';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

type PrioritiesListProps = {
    inventorySummary: InventorySummaryStats | null;
    canViewStock: boolean;
    canViewQuotes: boolean;
    canViewCash: boolean;
};

export function PrioritiesList({
    inventorySummary,
    canViewStock,
    canViewQuotes,
    canViewCash,
}: PrioritiesListProps) {
    const quotesQuery = usePendingQuotesSummary(canViewQuotes);
    const cashQuery = useCashSummary(undefined, canViewCash);
    
    // const pendingQuotes = quotesQuery.data?.total_pending ?? 0;
    const pendingQuotes = quotesQuery.data?.count ?? 0;
    const isCashClosed = canViewCash && !cashQuery.data?.session;
    const lowStock = inventorySummary?.low_stock ?? 0;
    // const pendingInvoices = 3; // Mocked for now until hook exists

    const priorities = [];

    if (isCashClosed) {
        priorities.push({
            id: 'cash',
            title: 'Abrir caja para comenzar a operar',
            href: '/app/cash',
            priority: 'high',
            icon: AlertTriangle,
            actionLabel: 'Abrir ahora'
        });
    }

    if (canViewQuotes && pendingQuotes > 0) {
        priorities.push({
            id: 'quotes',
            title: `Responder ${pendingQuotes} presupuestos pendientes`,
            href: '/app/gestion/ventas/presupuestos',
            priority: 'medium',
            icon: Clock,
            actionLabel: 'Ver todos'
        });
    }

    if (canViewStock && lowStock > 0) {
        priorities.push({
            id: 'stock',
            title: `Reponer ${lowStock} productos en stock crítico`,
            href: '/app/gestion/stock?status=low',
            priority: 'medium',
            icon: Box,
            actionLabel: 'Revisar stock'
        });
    }

    // Add a default positive state if empty
    if (priorities.length === 0) {
        return (
            <Card className="border-emerald-100 bg-emerald-50/50">
                <CardContent className="flex items-center gap-4 py-6">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
                        <CheckCircle className="h-6 w-6" />
                    </div>
                    <div>
                        <p className="font-medium text-emerald-900">Todo al día</p>
                        <p className="text-sm text-emerald-700">No hay prioridades urgentes pendientes.</p>
                    </div>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card>
            <CardHeader className="pb-3 border-b border-slate-100">
                <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-amber-500" />
                    Prioridades del día
                </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
                <div className="divide-y divide-slate-100">
                    {priorities.map((item) => (
                        <div key={item.id} className="flex items-center justify-between p-4 hover:bg-slate-50 transition-colors">
                            <div className="flex items-center gap-3">
                                <div className={cn(
                                    "flex h-9 w-9 items-center justify-center rounded-full",
                                    item.priority === 'high' ? "bg-red-100 text-red-600" : "bg-amber-100 text-amber-600"
                                )}>
                                    <item.icon className="h-5 w-5" />
                                </div>
                                <span className="text-sm font-medium text-slate-700">
                                    {item.title}
                                </span>
                            </div>
                            <Button variant="ghost" size="sm" asChild className="text-slate-500 hover:text-slate-900">
                                <Link href={item.href}>
                                    {item.actionLabel}
                                    <ArrowRight className="ml-1 h-3 w-3" />
                                </Link>
                            </Button>
                        </div>
                    ))}
                </div>
            </CardContent>
        </Card>
    );
}
