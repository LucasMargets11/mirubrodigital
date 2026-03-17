import {
    AlertTriangle,
    Box,
    CalendarClock,
    CalendarX2,
    CircleAlert,
    Clock,
    PackageX,
} from 'lucide-react';

import type { DashboardFinanceSummary } from '@/lib/api/treasury';

import type { DailyPriority } from './types';

// ── 1. Caja cerrada → critical ────────────────────────────────────────────────

export function buildCashClosedPriority(isCashClosed: boolean): DailyPriority | null {
    if (!isCashClosed) return null;
    return {
        id: 'cash-closed',
        title: 'Abrir caja para comenzar a operar',
        severity: 'critical',
        href: '/app/cash',
        actionLabel: 'Abrir ahora',
        icon: AlertTriangle,
    };
}

// ── 2. Presupuestos pendientes → important ────────────────────────────────────

export function buildPendingQuotesPriority(count: number): DailyPriority | null {
    if (count <= 0) return null;
    return {
        id: 'pending-quotes',
        title: `Responder ${count} presupuesto${count === 1 ? '' : 's'} pendiente${count === 1 ? '' : 's'}`,
        severity: 'important',
        href: '/app/gestion/ventas/presupuestos',
        actionLabel: 'Ver todos',
        icon: Clock,
        count,
    };
}

// ── 3. Stock bajo → important ─────────────────────────────────────────────────

export function buildLowStockPriority(count: number): DailyPriority | null {
    if (count <= 0) return null;
    return {
        id: 'low-stock',
        title: `Reponer ${count} producto${count === 1 ? '' : 's'} en stock crítico`,
        severity: 'important',
        href: '/app/gestion/stock?status=low',
        actionLabel: 'Revisar stock',
        icon: Box,
        count,
    };
}

// ── 4. Productos agotados / sin stock → urgent ───────────────────────────────

export function buildOutOfStockPriority(count: number): DailyPriority | null {
    if (count <= 0) return null;
    return {
        id: 'out-of-stock',
        title: `${count} producto${count === 1 ? '' : 's'} sin stock`,
        severity: 'urgent',
        href: '/app/gestion/stock?status=out',
        actionLabel: 'Ver productos',
        icon: PackageX,
        count,
    };
}

// ── 5. Gastos fijos vencidos del mes → critical ──────────────────────────────

export function buildOverdueFixedExpensesPriority(
    fixedPending: DashboardFinanceSummary['fixed_pending'],
): DailyPriority | null {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const overdueItems = fixedPending.items.filter((item) => {
        if (!item.due_date) return false;
        return new Date(item.due_date + 'T00:00:00') < today;
    });

    if (overdueItems.length === 0) return null;

    const totalAmount = overdueItems.reduce((sum, item) => sum + item.amount, 0);

    return {
        id: 'overdue-fixed-expenses',
        title: `${overdueItems.length} gasto${overdueItems.length === 1 ? '' : 's'} fijo${overdueItems.length === 1 ? '' : 's'} vencido${overdueItems.length === 1 ? '' : 's'}`,
        severity: 'critical',
        href: '/app/gestion/finanzas/gastos?tab=fijos',
        actionLabel: 'Pagar ahora',
        icon: CalendarX2,
        count: overdueItems.length,
        amount: totalAmount,
    };
}

// ── 6. Gastos puntuales vencidos → critical ──────────────────────────────────

export function buildOverdueOnetimeExpensesPriority(
    onetimePending: DashboardFinanceSummary['onetime_pending'],
): DailyPriority | null {
    const overdueItems = onetimePending.items.filter((item) => item.is_overdue);

    if (overdueItems.length === 0) return null;

    const totalAmount = overdueItems.reduce((sum, item) => sum + item.amount, 0);

    return {
        id: 'overdue-onetime-expenses',
        title: `${overdueItems.length} gasto${overdueItems.length === 1 ? '' : 's'} puntual${overdueItems.length === 1 ? '' : 'es'} vencido${overdueItems.length === 1 ? '' : 's'}`,
        severity: 'critical',
        href: '/app/gestion/finanzas/gastos?tab=puntuales',
        actionLabel: 'Pagar ahora',
        icon: CircleAlert,
        count: overdueItems.length,
        amount: totalAmount,
    };
}

// ── 7. Gastos fijos pendientes del mes (no vencidos) → important ─────────────

export function buildPendingFixedExpensesPriority(
    fixedPending: DashboardFinanceSummary['fixed_pending'],
): DailyPriority | null {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    // Count overdue items from the items array (ordered by due_date, max 10)
    const overdueFromItems = fixedPending.items.filter((item) => {
        if (!item.due_date) return false;
        return new Date(item.due_date + 'T00:00:00') < today;
    }).length;

    // Non-overdue = total pending minus overdue
    const pendingCount = fixedPending.total_count - overdueFromItems;

    if (pendingCount <= 0) return null;

    // Estimate non-overdue amount
    const overdueAmount = fixedPending.items
        .filter((item) => item.due_date && new Date(item.due_date + 'T00:00:00') < today)
        .reduce((sum, item) => sum + item.amount, 0);
    const pendingAmount = fixedPending.total_amount - overdueAmount;

    return {
        id: 'pending-fixed-expenses',
        title: `${pendingCount} gasto${pendingCount === 1 ? '' : 's'} fijo${pendingCount === 1 ? '' : 's'} pendiente${pendingCount === 1 ? '' : 's'} del mes`,
        severity: 'important',
        href: '/app/gestion/finanzas/gastos?tab=fijos',
        actionLabel: 'Revisar',
        icon: CalendarClock,
        count: pendingCount,
        amount: pendingAmount > 0 ? pendingAmount : undefined,
    };
}
