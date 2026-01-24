"use client";

import Link from 'next/link';
import { useMemo } from 'react';

import { useCashSummary } from '@/features/cash/hooks';
import { useInventorySummary, useSalesTodaySummary } from '@/features/gestion/hooks';
import type { InventorySummaryStats } from '@/features/gestion/types';
import { formatCurrency, formatNumber } from '@/lib/format';
import { cn } from '@/lib/utils';

type HealthCardsProps = {
    initialSummary: InventorySummaryStats | null;
    canViewStock: boolean;
    inventoryEnabled: boolean;
    canViewSales: boolean;
    salesEnabled: boolean;
    canViewCash: boolean;
    cashEnabled: boolean;
};

type CardConfig = {
    key: string;
    title: string;
    value: string;
    description: string;
    href?: string;
    badgeLabel?: string;
    badgeTone?: string;
    accent: string;
    barValue?: number | null;
    state?: 'ok' | 'warn' | 'alert' | 'info';
};

export function HealthCards({
    initialSummary,
    canViewStock,
    inventoryEnabled,
    canViewSales,
    salesEnabled,
    canViewCash,
    cashEnabled,
}: HealthCardsProps) {
    const inventoryQuery = useInventorySummary({
        initialData: canViewStock && inventoryEnabled ? initialSummary : null,
        enabled: canViewStock && inventoryEnabled,
    });
    const salesTodayQuery = useSalesTodaySummary(canViewSales && salesEnabled);
    const cashAccess = canViewCash && cashEnabled;
    const cashSummaryQuery = useCashSummary(undefined, cashAccess);
    const cashSession = cashSummaryQuery.data?.session ?? null;

    const summary = useMemo(() => {
        if (!canViewStock || !inventoryEnabled) {
            return null;
        }
        return inventoryQuery.data ?? initialSummary ?? null;
    }, [canViewStock, inventoryEnabled, inventoryQuery.data, initialSummary]);

    const totalProducts = summary?.total_products ?? null;
    const healthyRatio = summary?.healthy_ratio ?? null;
    const lowRatio = summary?.low_ratio ?? null;
    const outRatio = summary?.out_ratio ?? null;
    const lowCount = summary?.low_stock ?? null;
    const outCount = summary?.out_of_stock ?? null;

    const salesSnapshot = canViewSales && salesEnabled ? salesTodayQuery.data : null;

    const cards: CardConfig[] = [
        {
            key: 'published',
            title: 'Productos publicados',
            value: totalProducts !== null ? formatNumber(totalProducts) : '—',
            description: healthyRatio !== null ? `${Math.round(healthyRatio * 100)}% con stock sano` : 'Sin datos disponibles',
            href: canViewStock && inventoryEnabled ? '/app/gestion/productos' : undefined,
            badgeLabel: healthyRatio !== null && healthyRatio >= 0.7 ? 'OK' : 'Revisar',
            badgeTone: healthyRatio !== null && healthyRatio >= 0.7 ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700',
            accent: 'from-emerald-500/20 via-emerald-500/10 to-emerald-500/5',
            barValue: healthyRatio,
            state: healthyRatio !== null && healthyRatio >= 0.7 ? 'ok' : 'warn',
        },
        {
            key: 'low-stock',
            title: 'Stock crítico',
            value: lowCount !== null ? formatNumber(lowCount) : '—',
            description:
                lowRatio !== null && totalProducts
                    ? `${Math.round((lowRatio || 0) * 100)}% de catálogo` : 'Sin alertas registradas',
            href: canViewStock && inventoryEnabled ? '/app/gestion/stock?status=low' : undefined,
            badgeLabel: lowCount && lowCount > 0 ? 'Alerta' : 'OK',
            badgeTone: lowCount && lowCount > 0 ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-700',
            accent: 'from-amber-500/20 via-amber-500/10 to-amber-500/5',
            barValue: lowRatio,
            state: lowCount && lowCount > 0 ? 'warn' : 'ok',
        },
        {
            key: 'out-stock',
            title: 'Sin stock',
            value: outCount !== null ? formatNumber(outCount) : '—',
            description:
                outRatio !== null && totalProducts
                    ? `${Math.round((outRatio || 0) * 100)}% del catálogo` : 'Todo en orden',
            href: canViewStock && inventoryEnabled ? '/app/gestion/stock?status=out' : undefined,
            badgeLabel: outCount && outCount > 0 ? 'Crítico' : 'OK',
            badgeTone: outCount && outCount > 0 ? 'bg-rose-100 text-rose-700' : 'bg-emerald-100 text-emerald-700',
            accent: 'from-rose-500/20 via-rose-500/10 to-rose-500/5',
            barValue: outRatio,
            state: outCount && outCount > 0 ? 'alert' : 'ok',
        },
        {
            key: 'sales-today',
            title: 'Ventas hoy',
            value: salesSnapshot ? formatCurrency(salesSnapshot.total_amount) : 'Próximamente',
            description: salesSnapshot
                ? `${salesSnapshot.orders_count} operaciones • Ticket ${formatCurrency(salesSnapshot.average_ticket)}`
                : 'Activá ventas para verlo acá',
            href: salesSnapshot ? '/app/gestion/ventas' : undefined,
            badgeLabel: salesSnapshot ? 'En vivo' : 'Off',
            badgeTone: salesSnapshot ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-500',
            accent: 'from-sky-500/20 via-sky-500/10 to-indigo-500/10',
            barValue: salesSnapshot ? 1 : null,
            state: salesSnapshot ? 'info' : 'warn',
        },
    ];

    if (cashAccess && cashSession?.totals) {
        const sessionTotals = cashSession.totals;
        const sessionSalesCount = sessionTotals.sales_count ?? 0;
        const totalSalesToday = canViewSales && salesEnabled ? salesSnapshot?.orders_count ?? null : null;
        const progressValue =
            totalSalesToday && totalSalesToday > 0 ? Math.min(sessionSalesCount / totalSalesToday, 1) : null;
        const progressPercent = progressValue !== null ? Math.round(progressValue * 100) : null;

        cards.push({
            key: 'cash-session',
            title: 'Caja en curso',
            value: formatCurrency(sessionTotals.payments_total),
            description:
                progressPercent !== null
                    ? `${formatNumber(sessionSalesCount)} ventas cobradas · ${progressPercent}% del día`
                    : `${formatNumber(sessionSalesCount)} ventas cobradas en la sesión`,
            href: '/app/operacion/caja',
            badgeLabel: 'Caja abierta',
            badgeTone: 'bg-emerald-100 text-emerald-700',
            accent: 'from-emerald-500/20 via-emerald-500/10 to-emerald-500/5',
            barValue: progressValue,
            state: 'info',
        });
    }

    const averageCard: CardConfig | null = salesSnapshot
        ? {
            key: 'avg-ticket',
            title: 'Ticket promedio',
            value: formatCurrency(salesSnapshot.average_ticket),
            description: salesSnapshot.orders_count ? `${salesSnapshot.orders_count} ventas hoy` : 'Sin operaciones',
            href: '/app/gestion/ventas',
            badgeLabel: 'Tendencia',
            badgeTone: 'bg-violet-100 text-violet-700',
            accent: 'from-violet-500/15 via-violet-500/10 to-purple-500/10',
            barValue: null,
            state: 'info',
        }
        : null;

    if (averageCard) {
        cards.push(averageCard);
    }

    return (
        <section className="space-y-4">
            <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div>
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Salud Comercial</p>
                    <h1 className="text-2xl font-semibold text-slate-900">Panel rápido de señales</h1>
                </div>
                {summary ? (
                    <span className="text-sm text-slate-400">{summary.total_products} productos monitoreados</span>
                ) : null}
            </div>
            <div className="grid gap-4 lg:grid-cols-4">
                {cards.map((card) => (
                    <Card key={card.key} config={card} />
                ))}
            </div>
        </section>
    );
}

function Card({ config }: { config: CardConfig }) {
    const { title, value, description, href, badgeLabel, badgeTone, accent, barValue } = config;
    const disabled = !href;

    const content = (
        <div
            className={cn(
                'group relative flex flex-col gap-4 rounded-3xl border border-slate-100 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900/20',
                disabled && 'cursor-not-allowed opacity-70'
            )}
            aria-disabled={disabled}
        >
            <div>
                <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-slate-400">
                    <span>{title}</span>
                    {badgeLabel ? <span className={cn('rounded-full px-2 py-0.5 text-[11px]', badgeTone)}>{badgeLabel}</span> : null}
                </div>
                <p className="mt-2 text-3xl font-semibold text-slate-900">{value}</p>
                <p className="text-sm text-slate-500">{description}</p>
            </div>
            <div className="relative">
                <div className="h-2 w-full rounded-full bg-slate-100">
                    {typeof barValue === 'number' ? (
                        <div
                            className={cn('absolute inset-y-0 left-0 rounded-full bg-gradient-to-r', accent ? ` ${accent}` : ' from-slate-900/80 to-slate-900/60')}
                            style={{ width: `${Math.min(100, Math.max(0, Math.round(barValue * 100)))}%` }}
                        />
                    ) : null}
                </div>
            </div>
        </div>
    );

    if (href && !disabled) {
        return (
            <Link href={href} className="block focus-visible:outline-none focus-visible:ring-0">
                {content}
            </Link>
        );
    }

    return content;
}
