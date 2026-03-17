"use client";

import { ArrowRight, CheckCircle, Loader2 } from 'lucide-react';
import Link from 'next/link';

import type { InventorySummaryStats } from '@/features/gestion/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { formatCurrency } from '@/lib/format';

import { useDailyPriorities } from '../../priorities/use-daily-priorities';
import type { DailyPriority, PrioritySeverity } from '../../priorities/types';

type PrioritiesListProps = {
    inventorySummary: InventorySummaryStats | null;
    canViewStock: boolean;
    canViewQuotes: boolean;
    canViewCash: boolean;
    canViewFinance: boolean;
};

const SEVERITY_STYLES: Record<PrioritySeverity, { bg: string; text: string; dot: string }> = {
    critical: { bg: 'bg-red-100', text: 'text-red-600', dot: 'bg-red-500' },
    urgent: { bg: 'bg-orange-100', text: 'text-orange-600', dot: 'bg-orange-500' },
    important: { bg: 'bg-amber-100', text: 'text-amber-600', dot: 'bg-amber-500' },
    informative: { bg: 'bg-blue-100', text: 'text-blue-600', dot: 'bg-blue-500' },
};

export function PrioritiesList({
    inventorySummary,
    canViewStock,
    canViewQuotes,
    canViewCash,
    canViewFinance,
}: PrioritiesListProps) {
    const { priorities, isLoading } = useDailyPriorities({
        inventorySummary,
        canViewStock,
        canViewQuotes,
        canViewCash,
        canViewFinance,
    });

    if (isLoading) {
        return (
            <Card className="border-slate-100">
                <CardContent className="flex items-center justify-center gap-3 py-8">
                    <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
                    <p className="text-sm text-slate-500">Cargando prioridades…</p>
                </CardContent>
            </Card>
        );
    }

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

    // Use the highest severity to color the header dot
    const headerDotColor = SEVERITY_STYLES[priorities[0].severity].dot;

    return (
        <Card>
            <CardHeader className="pb-3 border-b border-slate-100">
                <CardTitle className="text-base font-semibold text-slate-800 flex items-center gap-2">
                    <span className={cn("h-2 w-2 rounded-full", headerDotColor)} />
                    Prioridades del día
                    <span className="ml-auto text-xs font-normal text-slate-400">
                        {priorities.length}
                    </span>
                </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
                <div className="divide-y divide-slate-100">
                    {priorities.map((item) => (
                        <PriorityRow key={item.id} item={item} />
                    ))}
                </div>
            </CardContent>
        </Card>
    );
}

function PriorityRow({ item }: { item: DailyPriority }) {
    const style = SEVERITY_STYLES[item.severity];

    return (
        <div className="flex items-center justify-between p-4 hover:bg-slate-50 transition-colors">
            <div className="flex items-center gap-3 min-w-0 flex-1">
                <div className={cn(
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
                    style.bg,
                    style.text,
                )}>
                    <item.icon className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                    <span className="text-sm font-medium text-slate-700 line-clamp-1">
                        {item.title}
                    </span>
                    {item.amount != null && item.amount > 0 && (
                        <span className="text-xs text-slate-500">
                            {formatCurrency(item.amount)}
                        </span>
                    )}
                </div>
            </div>
            <Button variant="ghost" size="sm" asChild className="shrink-0 text-slate-500 hover:text-slate-900">
                <Link href={item.href as any}>
                    {item.actionLabel}
                    <ArrowRight className="ml-1 h-3 w-3" />
                </Link>
            </Button>
        </div>
    );
}
