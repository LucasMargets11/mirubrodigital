"use client";

import { useQuery } from '@tanstack/react-query';

import { useCashSummary } from '@/features/cash/hooks';
import { usePendingQuotesSummary } from '@/features/gestion/hooks';
import type { InventorySummaryStats } from '@/features/gestion/types';
import { getDashboardFinanceSummary } from '@/lib/api/treasury';

import {
    buildCashClosedPriority,
    buildLowStockPriority,
    buildOutOfStockPriority,
    buildOverdueFixedExpensesPriority,
    buildOverdueOnetimeExpensesPriority,
    buildPendingFixedExpensesPriority,
    buildPendingQuotesPriority,
} from './builders';
import type { DailyPriority } from './types';
import { SEVERITY_ORDER } from './types';

type UseDailyPrioritiesParams = {
    inventorySummary: InventorySummaryStats | null;
    canViewStock: boolean;
    canViewQuotes: boolean;
    canViewCash: boolean;
    canViewFinance: boolean;
};

export function useDailyPriorities({
    inventorySummary,
    canViewStock,
    canViewQuotes,
    canViewCash,
    canViewFinance,
}: UseDailyPrioritiesParams) {
    const quotesQuery = usePendingQuotesSummary(canViewQuotes);
    const cashQuery = useCashSummary(undefined, canViewCash);

    const financeQuery = useQuery({
        queryKey: ['treasury', 'dashboard-finance-summary'],
        queryFn: getDashboardFinanceSummary,
        enabled: canViewFinance,
        staleTime: 2 * 60 * 1000,
    });

    const isLoading =
        (canViewQuotes && quotesQuery.isLoading) ||
        (canViewCash && cashQuery.isLoading) ||
        (canViewFinance && financeQuery.isLoading);

    const priorities: DailyPriority[] = [];

    // 1. Caja cerrada
    const cash = buildCashClosedPriority(canViewCash && !cashQuery.data?.session);
    if (cash) priorities.push(cash);

    // 5. Gastos fijos vencidos del mes
    if (canViewFinance && financeQuery.data) {
        const overdueFixed = buildOverdueFixedExpensesPriority(financeQuery.data.fixed_pending);
        if (overdueFixed) priorities.push(overdueFixed);
    }

    // 6. Gastos puntuales vencidos
    if (canViewFinance && financeQuery.data) {
        const overdueOnetime = buildOverdueOnetimeExpensesPriority(financeQuery.data.onetime_pending);
        if (overdueOnetime) priorities.push(overdueOnetime);
    }

    // 4. Productos agotados / sin stock
    if (canViewStock) {
        const outOfStock = buildOutOfStockPriority(inventorySummary?.out_of_stock ?? 0);
        if (outOfStock) priorities.push(outOfStock);
    }

    // 3. Stock bajo
    if (canViewStock) {
        const lowStock = buildLowStockPriority(inventorySummary?.low_stock ?? 0);
        if (lowStock) priorities.push(lowStock);
    }

    // 2. Presupuestos pendientes
    if (canViewQuotes) {
        const quotes = buildPendingQuotesPriority(quotesQuery.data?.count ?? 0);
        if (quotes) priorities.push(quotes);
    }

    // 7. Gastos fijos pendientes del mes (no vencidos)
    if (canViewFinance && financeQuery.data) {
        const pendingFixed = buildPendingFixedExpensesPriority(financeQuery.data.fixed_pending);
        if (pendingFixed) priorities.push(pendingFixed);
    }

    // Sort by severity (critical first)
    priorities.sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);

    return { priorities, isLoading };
}
