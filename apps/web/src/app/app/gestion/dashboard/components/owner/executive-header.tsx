"use client";

import { Calendar } from 'lucide-react';
import { useMemo } from 'react';

import { usePendingQuotesSummary, useSalesTodaySummary } from '@/features/gestion/hooks';
import { useCashSummary } from '@/features/cash/hooks';
import type { InventorySummaryStats } from '@/features/gestion/types';
import { formatCurrency, formatNumber } from '@/lib/format';

type ExecutiveHeaderProps = {
    inventorySummary: InventorySummaryStats | null;
    canViewSales: boolean;
    canViewCash: boolean;
    canViewQuotes: boolean;
    canViewStock: boolean;
};

export function ExecutiveHeader({
    inventorySummary,
    canViewSales,
    canViewCash,
    canViewQuotes,
    canViewStock
}: ExecutiveHeaderProps) {
    const salesQuery = useSalesTodaySummary(canViewSales);
    const quotesQuery = usePendingQuotesSummary(canViewQuotes);
    const cashQuery = useCashSummary(undefined, canViewCash);

    // Adapting to actual hook return type { count: number }
    const pendingQuotes = quotesQuery.data?.count ?? 0;
    // const pendingAmount = 0; // Not available in current hook
    const cashStatus = cashQuery.data?.session ? 'abierta' : 'cerrada';
    const lowStock = inventorySummary?.low_stock ?? 0;

    const summaryLine = useMemo(() => {
        const parts = [];
        
        if (canViewQuotes && pendingQuotes > 0) {
            parts.push(`Tienes ${pendingQuotes} presupuestos pendientes por procesar`);
        } else if (canViewSales && (Number(salesQuery.data?.orders_count) || 0) > 0) {
            parts.push(`Hoy se realizaron ${salesQuery.data?.orders_count} ventas`);
        } else {
            parts.push("Sin actividad comercial significativa hoy");
        }

        if (canViewCash) {
            parts.push(`caja ${cashStatus}`);
        }

        if (canViewStock && lowStock > 0) {
            parts.push(`${lowStock} alertas de stock`);
        } else if (canViewStock) {
            parts.push("catálogo saludable");
        }

        return parts.join(', ');
    }, [pendingQuotes, salesQuery.data, cashStatus, lowStock, canViewQuotes, canViewSales, canViewCash, canViewStock]);

    return (
        <div className="flex flex-col gap-4 border-b border-gray-100 pb-6 md:flex-row md:items-end md:justify-between">
            <div className="space-y-1">
                <div className="flex items-center gap-2">
                    <h1 className="text-2xl font-bold tracking-tight text-slate-900">
                        Tablero Comercial
                    </h1>
                    <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600">
                        Owner
                    </span>
                </div>
                <p className="text-sm text-slate-500 first-letter:uppercase">
                    {summaryLine}.
                </p>
            </div>
            
            <div className="flex items-center gap-2">
                <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 shadow-sm">
                    <Calendar className="h-4 w-4 text-slate-400" />
                    <span>Hoy</span>
                </div>
                {/* Future: Add date range picker here */}
            </div>
        </div>
    );
}
