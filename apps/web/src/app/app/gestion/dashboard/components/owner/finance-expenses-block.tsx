"use client";

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import {
    ArrowRight,
    Receipt,
    CalendarClock,
    AlertTriangle,
    CircleDollarSign,
    TrendingDown,
} from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { getDashboardFinanceSummary } from '@/lib/api/treasury';
import type { DashboardFinanceSummaryItem } from '@/lib/api/treasury';
import { formatCurrency } from '@/lib/format';
import { cn } from '@/lib/utils';

type FinanceExpensesBlockProps = {
    canViewFinance: boolean;
};

export function FinanceExpensesBlock({ canViewFinance }: FinanceExpensesBlockProps) {
    const { data, isLoading, error } = useQuery({
        queryKey: ['treasury', 'dashboard-finance-summary'],
        queryFn: getDashboardFinanceSummary,
        enabled: canViewFinance,
        staleTime: 2 * 60 * 1000, // 2 minutes
    });

    if (!canViewFinance) return null;

    if (isLoading) return <FinanceExpensesSkeleton />;

    if (error) {
        return (
            <Card className="border-red-100 bg-red-50/30">
                <CardContent className="flex flex-col items-center justify-center p-6 text-center">
                    <AlertTriangle className="h-6 w-6 text-red-400 mb-2" />
                    <p className="text-sm font-medium text-red-700">No se pudo cargar el resumen de finanzas</p>
                    <p className="text-xs text-red-500 mt-1">Intentá de nuevo más tarde</p>
                </CardContent>
            </Card>
        );
    }

    if (!data) return null;

    const { expenses_summary, fixed_pending, onetime_pending } = data;
    const hasData = expenses_summary.total_count > 0 || fixed_pending.total_count > 0 || onetime_pending.total_count > 0;

    if (!hasData) {
        return (
            <Card className="border-slate-100 bg-slate-50/30">
                <CardHeader className="flex flex-row items-center justify-between pb-2 border-b border-slate-100">
                    <CardTitle className="text-base font-semibold text-slate-900 flex items-center gap-2">
                        <Receipt className="h-5 w-5 text-slate-500" />
                        Gastos del Mes
                    </CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col items-center justify-center p-6 text-center">
                    <CircleDollarSign className="h-8 w-8 text-slate-300 mb-2" />
                    <p className="text-sm font-medium text-slate-500">Sin gastos registrados</p>
                    <p className="text-xs text-slate-400 mt-1">Los gastos del mes aparecerán aquí</p>
                    <Button variant="link" asChild className="mt-2 text-indigo-600 text-sm">
                        <Link href="/app/gestion/finanzas/gastos">Registrar gasto</Link>
                    </Button>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="border-slate-200">
            <CardHeader className="flex flex-row items-center justify-between pb-2 border-b border-slate-100">
                <CardTitle className="text-base font-semibold text-slate-900 flex items-center gap-2">
                    <Receipt className="h-5 w-5 text-slate-500" />
                    Gastos del Mes
                </CardTitle>
                <Button variant="ghost" size="sm" asChild className="text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50">
                    <Link href="/app/gestion/finanzas/resumen">
                        Ver todo <ArrowRight className="ml-1 h-3 w-3" />
                    </Link>
                </Button>
            </CardHeader>

            <CardContent className="pt-5 space-y-5">
                {/* A. Resumen de Gastos del Mes */}
                <div>
                    <div className="flex items-baseline justify-between mb-3">
                        <p className="text-sm font-medium text-slate-500">Total egresos</p>
                        <span className="text-xs text-slate-400">{expenses_summary.total_count} registros</span>
                    </div>
                    <p className="text-2xl font-bold tracking-tight text-slate-900">
                        {formatCurrency(expenses_summary.total_amount)}
                    </p>
                    {(expenses_summary.fixed_count > 0 || expenses_summary.onetime_count > 0) && (
                        <div className="mt-2 flex gap-4">
                            {expenses_summary.fixed_count > 0 && (
                                <div className="flex items-center gap-1.5 text-xs text-slate-500">
                                    <span className="h-2 w-2 rounded-full bg-blue-400" />
                                    Fijos: {formatCurrency(expenses_summary.fixed_amount)}
                                </div>
                            )}
                            {expenses_summary.onetime_count > 0 && (
                                <div className="flex items-center gap-1.5 text-xs text-slate-500">
                                    <span className="h-2 w-2 rounded-full bg-amber-400" />
                                    Puntuales: {formatCurrency(expenses_summary.onetime_amount)}
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* B. Gastos Fijos Pendientes */}
                {fixed_pending.total_count > 0 && (
                    <PendingSection
                        title="Fijos pendientes del mes"
                        icon={CalendarClock}
                        totalCount={fixed_pending.total_count}
                        totalAmount={fixed_pending.total_amount}
                        items={fixed_pending.items}
                        iconColor="text-blue-500"
                        badgeColor="bg-blue-50 text-blue-700"
                        itemHref="/app/gestion/finanzas/gastos?tab=fijos"
                    />
                )}

                {/* C. Gastos Puntuales No Pagados */}
                {onetime_pending.total_count > 0 && (
                    <PendingSection
                        title="Puntuales sin pagar"
                        icon={TrendingDown}
                        totalCount={onetime_pending.total_count}
                        totalAmount={onetime_pending.total_amount}
                        items={onetime_pending.items}
                        iconColor="text-amber-500"
                        badgeColor="bg-amber-50 text-amber-700"
                        itemHref="/app/gestion/finanzas/gastos?tab=puntuales"
                    />
                )}
            </CardContent>
        </Card>
    );
}

// ── Pending Section sub-component ──────────────────────────────────────────────

type PendingSectionProps = {
    title: string;
    icon: React.ComponentType<{ className?: string }>;
    totalCount: number;
    totalAmount: number;
    items: DashboardFinanceSummaryItem[];
    iconColor: string;
    badgeColor: string;
    itemHref: string;
};

function PendingSection({
    title,
    icon: Icon,
    totalCount,
    totalAmount,
    items,
    iconColor,
    badgeColor,
    itemHref,
}: PendingSectionProps) {
    return (
        <div className="border-t border-slate-100 pt-4">
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    <Icon className={cn("h-4 w-4", iconColor)} />
                    <p className="text-sm font-semibold text-slate-700">{title}</p>
                </div>
                <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full", badgeColor)}>
                    {totalCount}
                </span>
            </div>
            <p className="text-lg font-bold text-slate-900 mb-2">
                {formatCurrency(totalAmount)}
            </p>
            <div className="space-y-1.5">
                {items.map((item) => (
                    <Link
                        key={item.id}
                        href={itemHref as any}
                        className="flex items-center justify-between py-1.5 px-2 rounded-md hover:bg-slate-50 transition-colors group"
                    >
                        <div className="min-w-0 flex-1">
                            <p className="text-sm text-slate-700 truncate group-hover:text-indigo-600 transition-colors">{item.name}</p>
                            {item.due_date && (
                                <p className={cn(
                                    "text-xs",
                                    item.is_overdue ? "text-red-500 font-medium" : "text-slate-400"
                                )}>
                                    {item.is_overdue && "⚠ "}
                                    {formatDate(item.due_date)}
                                </p>
                            )}
                        </div>
                        <span className="text-sm font-semibold text-slate-700 ml-3 shrink-0">
                            {formatCurrency(item.amount)}
                        </span>
                    </Link>
                ))}
                {totalCount > items.length && (
                    <Link
                        href={itemHref as any}
                        className="block text-xs text-slate-400 text-center pt-1 hover:text-indigo-500 transition-colors"
                    >
                        +{totalCount - items.length} más
                    </Link>
                )}
            </div>
        </div>
    );
}

// ── Skeleton ───────────────────────────────────────────────────────────────────

function FinanceExpensesSkeleton() {
    return (
        <Card className="border-slate-100 animate-pulse">
            <CardHeader className="pb-2">
                <div className="h-6 w-36 bg-slate-100 rounded" />
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="h-4 w-24 bg-slate-100 rounded" />
                <div className="h-8 w-32 bg-slate-100 rounded" />
                <div className="border-t border-slate-50 pt-3 space-y-2">
                    <div className="h-4 w-40 bg-slate-50 rounded" />
                    <div className="h-6 w-28 bg-slate-50 rounded" />
                    <div className="h-8 w-full bg-slate-50 rounded" />
                    <div className="h-8 w-full bg-slate-50 rounded" />
                </div>
            </CardContent>
        </Card>
    );
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
    const d = new Date(iso + 'T00:00:00');
    return d.toLocaleDateString('es-AR', { day: 'numeric', month: 'short' });
}
