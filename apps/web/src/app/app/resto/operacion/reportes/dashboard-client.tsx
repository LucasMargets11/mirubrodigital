'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import { AccessMessage } from '@/components/app/access-message';
import { ChartCard } from '@/components/reports/charts/ChartCard';
import { PaymentsDonutChart } from '@/components/reports/charts/PaymentsDonutChart';
import { SalesTrendChart } from '@/components/reports/charts/SalesTrendChart';
import { MetricCard } from '@/components/reports/metrics/MetricCard';
import { calculateDeltaPct, getToneFromDelta } from '@/components/reports/metrics/utils';
import type { MetricTone } from '@/components/reports/metrics/utils';
import type { TrendPoint } from '@/components/reports/utils/fillMissingPeriods';
import { formatDateShort } from '@/components/reports/utils/format';
import type { CashClosure, PaymentBreakdownRow } from '@/features/reports/types';
import { ApiError } from '@/lib/api/client';
import { formatCurrency, formatNumber } from '@/lib/format';
import { ReportsFilters, type ReportsFiltersValue } from '@/modules/reports/components/filters';

import {
    useRestaurantReportsCashSessions,
    useRestaurantReportsProducts,
    useRestaurantReportsSummary,
} from '@/features/resto-reports/hooks';
import type {
    RestaurantProductRow,
    RestaurantReportsSummaryKPIs,
} from '@/features/resto-reports/types';

const defaultRange = getDefaultRange();
const integerCurrencyFormatter = new Intl.NumberFormat('es-AR', {
    style: 'currency',
    currency: 'ARS',
    maximumFractionDigits: 0,
});
const metricsConfig: MetricConfig[] = [
    { key: 'revenue_total', label: 'Facturación total', format: 'currency', betterWhenHigher: true },
    { key: 'sales_count', label: 'Ventas completadas', format: 'number', betterWhenHigher: true },
    { key: 'avg_ticket', label: 'Ticket promedio', format: 'currency', betterWhenHigher: true },
    { key: 'cash_sessions_closed', label: 'Cajas cerradas', format: 'number', betterWhenHigher: true },
    { key: 'cash_diff_total', label: 'Diferencia total de caja', format: 'currency', betterWhenHigher: false },
];

export function RestauranteReportsDashboard() {
    const [filters, setFilters] = useState<ReportsFiltersValue>({
        preset: 'last7',
        from: defaultRange.from,
        to: defaultRange.to,
    });
    const [compare, setCompare] = useState(false);
    const [accessDenied, setAccessDenied] = useState(false);

    const summaryParams = useMemo(() => {
        if (!filters.from || !filters.to) {
            return null;
        }
        return {
            date_from: filters.from,
            date_to: filters.to,
            compare,
        };
    }, [filters.from, filters.to, compare]);

    const baseEnabled = Boolean(summaryParams) && !accessDenied;

    const summaryQuery = useRestaurantReportsSummary(summaryParams, { enabled: baseEnabled });
    const productsQuery = useRestaurantReportsProducts(
        summaryParams
            ? {
                date_from: summaryParams.date_from,
                date_to: summaryParams.date_to,
                limit: 10,
            }
            : null,
        { enabled: baseEnabled },
    );
    const cashSessionsQuery = useRestaurantReportsCashSessions(
        summaryParams
            ? {
                date_from: summaryParams.date_from,
                date_to: summaryParams.date_to,
                limit: 10,
            }
            : null,
        { enabled: baseEnabled },
    );

    useEffect(() => {
        if (summaryQuery.error instanceof ApiError && summaryQuery.error.status === 403) {
            setAccessDenied(true);
        }
    }, [summaryQuery.error]);

    if (accessDenied) {
        return (
            <AccessMessage
                title="Sin acceso a reportes"
                description="Tu usuario no tiene permisos para ver los reportes de operación."
                hint="Pedí acceso a un administrador"
            />
        );
    }

    const summary = summaryQuery.data;
    const compareKpis = summary?.compare?.kpis;
    const metrics = buildMetricViews(metricsConfig, summary?.kpis, compareKpis);
    const metricsLoading = summaryQuery.isLoading;
    const paymentsChartData = useMemo<PaymentBreakdownRow[]>(
        () => (summary?.payments ?? []).map(convertPaymentRow),
        [summary?.payments],
    );
    const trendSeries = useMemo<TrendPoint[]>(
        () => (summary?.series_daily ?? []).map(convertTrendPoint),
        [summary?.series_daily],
    );
    const productsData = productsQuery.data;
    const cashSessions = cashSessionsQuery.data?.results ?? [];
    const rangeLabel = summary?.range
        ? formatRangeLabel(summary.range.date_from, summary.range.date_to)
        : formatRangeLabel(filters.from, filters.to);

    return (
        <div className="space-y-6">
            <div className="space-y-2">
                <ReportsFilters value={filters} onChange={setFilters} />
                <label className="flex items-center gap-2 text-sm font-medium text-slate-600">
                    <input
                        type="checkbox"
                        checked={compare}
                        onChange={(event) => setCompare(event.target.checked)}
                        className="h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-400"
                    />
                    Comparar con período anterior
                </label>
            </div>

            {summaryQuery.isError &&
                !summaryQuery.isLoading &&
                !(summaryQuery.error instanceof ApiError && summaryQuery.error.status === 403) && (
                    <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                        No pudimos cargar los reportes. Intentá nuevamente en unos minutos.
                    </div>
                )}

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
                {metrics.map((metric) => (
                    <MetricCard
                        key={metric.key}
                        title={metric.label}
                        value={metric.value}
                        deltaPct={metric.deltaPct}
                        tone={metric.tone}
                        loading={metricsLoading}
                    />
                ))}
            </div>

            <div className="grid gap-4 lg:grid-cols-3">
                <div className="space-y-4 lg:col-span-2">
                    <ChartCard
                        title="Facturación diaria"
                        totalValue={summary?.kpis.revenue_total}
                        subtitle={rangeLabel}
                        loading={summaryQuery.isLoading}
                        isEmpty={!trendSeries.length}
                    >
                        <SalesTrendChart data={trendSeries} />
                    </ChartCard>
                </div>
                <ChartCard
                    title="Cobros por medio"
                    totalValue={summary?.kpis.revenue_total}
                    subtitle={rangeLabel}
                    loading={summaryQuery.isLoading}
                    isEmpty={!paymentsChartData.length}
                    emptyText="Sin cobros registrados en este período"
                    rightSlot={<TopPaymentBadge method={summary?.kpis.top_payment_method} />}
                    height={340}
                >
                    <PaymentsDonutChart data={paymentsChartData} topN={4} />
                </ChartCard>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
                <ProductsTable
                    title="Top productos"
                    rows={productsData?.top ?? []}
                    loading={productsQuery.isLoading}
                    emptyMessage="Sin ventas registradas en el período."
                />
                <ProductsTable
                    title="Menos pedidos"
                    rows={productsData?.bottom ?? []}
                    loading={productsQuery.isLoading}
                    emptyMessage="Sin ventas registradas en el período."
                />
            </div>

            <RecentCashSessionsTable
                rows={cashSessions}
                loading={cashSessionsQuery.isLoading}
            />
        </div>
    );
}

type MetricConfig = {
    key: keyof RestaurantReportsSummaryKPIs;
    label: string;
    format: 'currency' | 'number';
    betterWhenHigher: boolean;
};

type MetricView = {
    key: string;
    label: string;
    value: string;
    deltaPct: number | null;
    tone: MetricTone;
};

function buildMetricViews(
    config: MetricConfig[],
    current?: RestaurantReportsSummaryKPIs,
    previous?: RestaurantReportsSummaryKPIs,
): MetricView[] {
    return config.map((definition) => {
        const currentValue = current?.[definition.key];
        const previousValue = previous?.[definition.key];
        const numericCurrent = toNumber(currentValue);
        const numericPrevious = toNumber(previousValue);
        const deltaPct = previous ? calculateDeltaPct(numericCurrent, numericPrevious) : null;
        const tone = resolveTone(deltaPct, definition.betterWhenHigher);
        const value = definition.format === 'currency' ? formatCurrency(numericCurrent) : formatNumber(numericCurrent);
        return {
            key: definition.key,
            label: definition.label,
            value,
            deltaPct,
            tone,
        };
    });
}

function resolveTone(deltaPct: number | null, betterWhenHigher: boolean): MetricTone {
    if (deltaPct === null) {
        return 'neutral';
    }
    const tone = getToneFromDelta(deltaPct);
    if (betterWhenHigher) {
        return tone;
    }
    if (tone === 'positive') {
        return 'negative';
    }
    if (tone === 'negative') {
        return 'positive';
    }
    return tone;
}

function convertPaymentRow(row: { method: string; method_label: string; amount: string; count: number }): PaymentBreakdownRow {
    return {
        method: row.method,
        method_label: row.method_label,
        amount_total: row.amount,
        payments_count: row.count,
        sales_count: row.count,
    };
}

function convertTrendPoint(point: { date: string; revenue: string; sales_count: number }): TrendPoint {
    const total = toNumber(point.revenue);
    const count = point.sales_count || 0;
    const avg = count ? total / count : 0;
    return {
        period: point.date,
        gross_sales: point.revenue,
        sales_count: point.sales_count,
        avg_ticket: avg.toFixed(2),
    };
}

function getDefaultRange() {
    const to = new Date();
    const from = new Date();
    from.setDate(to.getDate() - 6);
    return { from: toIso(from), to: toIso(to) };
}

function toIso(date: Date) {
    return date.toISOString().slice(0, 10);
}

function toNumber(value: unknown): number {
    if (value === null || value === undefined) {
        return 0;
    }
    if (typeof value === 'number') {
        return Number.isFinite(value) ? value : 0;
    }
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
}

function formatRangeLabel(from?: string, to?: string) {
    if (!from || !to) {
        return undefined;
    }
    return `${formatDateShort(from)} – ${formatDateShort(to)}`;
}

function formatCurrencyInteger(value: unknown) {
    const rounded = Math.round(toNumber(value));
    return integerCurrencyFormatter.format(rounded);
}

function TopPaymentBadge({ method }: { method?: RestaurantReportsSummaryKPIs['top_payment_method'] }) {
    if (!method) {
        return null;
    }
    return (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2 text-sm text-slate-700">
            <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Principal</p>
            <p className="font-semibold text-slate-900">{method.method_label}</p>
            <p className="text-xs text-slate-500">{formatCurrency(toNumber(method.amount))}</p>
        </div>
    );
}

type ProductsTableProps = {
    title: string;
    rows: RestaurantProductRow[];
    loading: boolean;
    emptyMessage: string;
};

function ProductsTable({ title, rows, loading, emptyMessage }: ProductsTableProps) {
    return (
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
                <span className="text-xs uppercase tracking-[0.3em] text-slate-400">Productos</span>
            </div>
            <div className="mt-4 overflow-x-auto">
                {loading ? (
                    <div className="h-36 animate-pulse rounded-2xl bg-slate-100" />
                ) : rows.length ? (
                    <table className="min-w-full text-sm">
                        <thead>
                            <tr className="text-left text-slate-500">
                                <th className="px-3 py-2 font-medium">Producto</th>
                                <th className="px-3 py-2 text-right font-medium">Cantidad</th>
                                <th className="px-3 py-2 text-right font-medium">Total</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {rows.map((row) => (
                                <tr key={`${row.product_id ?? row.name}`}>
                                    <td className="px-3 py-3 font-semibold text-slate-900">{row.name}</td>
                                    <td className="px-3 py-3 text-right text-slate-600">{row.qty}</td>
                                    <td className="px-3 py-3 text-right font-semibold text-slate-900">{formatCurrencyInteger(row.revenue)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                ) : (
                    <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/70 p-6 text-center text-sm text-slate-500">
                        {emptyMessage}
                    </div>
                )}
            </div>
        </section>
    );
}

type RecentCashSessionsTableProps = {
    rows: CashClosure[];
    loading: boolean;
};

function RecentCashSessionsTable({ rows, loading }: RecentCashSessionsTableProps) {
    return (
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                    <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Caja</p>
                    <h2 className="text-lg font-semibold text-slate-900">Cajas recientes</h2>
                </div>
                <Link
                    href="/app/resto/operacion/reportes/caja"
                    className="text-sm font-semibold text-slate-900 underline-offset-4 hover:underline"
                >
                    Ver todas
                </Link>
            </div>
            <div className="mt-4 overflow-x-auto">
                {loading ? (
                    <div className="h-40 animate-pulse rounded-2xl bg-slate-100" />
                ) : rows.length ? (
                    <table className="min-w-full text-sm">
                        <thead>
                            <tr className="text-left text-slate-500">
                                <th className="px-2 py-2 font-medium">Caja</th>
                                <th className="px-2 py-2 font-medium">Apertura</th>
                                <th className="px-2 py-2 font-medium">Cierre</th>
                                <th className="px-2 py-2 text-right font-medium">Diferencia</th>
                                <th className="px-2 py-2" />
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {rows.map((session) => (
                                <tr key={session.id}>
                                    <td className="px-2 py-3">
                                        <p className="font-semibold text-slate-900">{session.register?.name ?? '—'}</p>
                                        <p className="text-xs text-slate-500">{session.opened_by_name || session.opened_by?.name || '—'}</p>
                                    </td>
                                    <td className="px-2 py-3 text-slate-600">{formatDateTime(session.opened_at)}</td>
                                    <td className="px-2 py-3 text-slate-600">{session.closed_at ? formatDateTime(session.closed_at) : 'Sesión abierta'}</td>
                                    <td className={`px-2 py-3 text-right font-semibold ${differenceTone(session.difference)}`}>
                                        {formatCurrencyInteger(session.difference)}
                                    </td>
                                    <td className="px-2 py-3 text-right">
                                        <Link
                                            href={`/app/resto/operacion/reportes/caja/${session.id}`}
                                            className="text-sm font-medium text-slate-900 underline-offset-4 hover:underline"
                                        >
                                            Detalle
                                        </Link>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                ) : (
                    <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/70 p-6 text-center text-sm text-slate-500">
                        No hay sesiones cerradas en el rango.
                    </div>
                )}
            </div>
        </section>
    );
}

function formatDateTime(value: string) {
    try {
        return new Intl.DateTimeFormat('es-AR', {
            dateStyle: 'medium',
            timeStyle: 'short',
        }).format(new Date(value));
    } catch (error) {
        return value;
    }
}

function differenceTone(value?: string | null) {
    const numeric = toNumber(value);
    if (numeric === 0) {
        return 'text-slate-500';
    }
    return numeric > 0 ? 'text-rose-600' : 'text-emerald-600';
}
