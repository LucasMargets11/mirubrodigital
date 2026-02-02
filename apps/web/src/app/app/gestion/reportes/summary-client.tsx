'use client';

import { useMemo, useState } from 'react';

import { ChartCard } from '@/components/reports/charts/ChartCard';
import { PaymentsDonutChart } from '@/components/reports/charts/PaymentsDonutChart';
import { SalesTrendChart } from '@/components/reports/charts/SalesTrendChart';
import { InsightsRow } from '@/components/reports/insights/InsightsRow';
import type { Insight } from '@/components/reports/insights/InsightsRow';
import { MetricCard } from '@/components/reports/metrics/MetricCard';
import {
    calculateDeltaPct,
    formatDeltaLabel,
    getToneFromDelta,
} from '@/components/reports/metrics/utils';
import { fillMissingPeriods } from '@/components/reports/utils/fillMissingPeriods';
import type { TrendPoint } from '@/components/reports/utils/fillMissingPeriods';
import { formatDateLong, formatDateShort, toNumber } from '@/components/reports/utils/format';
import { useReportsSummary } from '@/features/reports/hooks';
import type {
    PaymentBreakdownRow,
    ReportSummaryResponse,
    ReportsFilters as ReportsFiltersParams,
} from '@/features/reports/types';
import { downloadCsv } from '@/lib/csv';
import { formatCurrency, formatNumber } from '@/lib/format';

import { ReportsFilters, type ReportsFiltersValue } from '@/modules/reports/components/filters';
import { StockAlertsWidget } from './components/stock-alerts-widget';
import { TopProductsWidget } from './components/top-products-widget';

type MetricDefinition = {
    key: string;
    title: string;
    type: 'currency' | 'number';
    getValue: (summary?: ReportSummaryResponse) => string | number | null | undefined;
};

type KpiKey = keyof ReportSummaryResponse['kpis'];

type ReportsSummaryClientProps = {
    canViewStock: boolean;
    hasInventoryFeature: boolean;
};

const DAY_IN_MS = 24 * 60 * 60 * 1000;

const defaultRange = getDefaultRange();

const metricDefinitions: MetricDefinition[] = [
    {
        key: 'gross_sales_total',
        title: 'Ventas brutas',
        type: 'currency',
        getValue: (summary) => summary?.kpis?.gross_sales_total,
    },
    {
        key: 'sales_count',
        title: 'Cantidad de ventas',
        type: 'number',
        getValue: (summary) => summary?.kpis?.sales_count,
    },
    {
        key: 'avg_ticket',
        title: 'Ticket promedio',
        type: 'currency',
        getValue: (summary) => summary?.kpis?.avg_ticket,
    },
    {
        key: 'units_sold',
        title: 'Unidades vendidas',
        type: 'number',
        getValue: (summary) => summary?.kpis?.units_sold,
    },
    {
        key: 'cash_total',
        title: 'Efectivo',
        type: 'currency',
        getValue: (summary) => {
            const breakdown = summary?.payments_breakdown ?? [];
            const cashRow = breakdown.find((row) => row.method === 'CASH');
            return cashRow?.amount_total ?? null;
        },
    },
];
const kpiDefinitions: Array<{ key: KpiKey; label: string }> = [
    { key: 'gross_sales_total', label: 'Ventas brutas' },
    { key: 'net_sales_total', label: 'Ventas netas' },
    { key: 'discounts_total', label: 'Descuentos aplicados' },
    { key: 'sales_count', label: 'Cantidad de ventas' },
    { key: 'avg_ticket', label: 'Ticket promedio' },
    { key: 'units_sold', label: 'Unidades vendidas' },
    { key: 'cancellations_count', label: 'Cancelaciones' },
];

export function ReportsSummaryClient({
    canViewStock,
    hasInventoryFeature,
}: ReportsSummaryClientProps) {
    const [filters, setFilters] = useState<ReportsFiltersValue>({
        preset: 'last7',
        from: defaultRange.from,
        to: defaultRange.to,
        groupBy: 'day',
    });

    const queryFilters = useMemo<ReportsFiltersParams>(
        () => ({
            from: filters.from,
            to: filters.to,
            group_by: filters.groupBy,
            status: filters.status,
            payment_method: filters.paymentMethod,
            method: filters.method,
            user_id: filters.userId,
            register_id: filters.registerId,
        }),
        [filters],
    );

    const previousFilters = useMemo<ReportsFiltersParams | null>(() => {
        if (!filters.from || !filters.to) {
            return null;
        }
        const prevRange = getPreviousRange(filters.from, filters.to);
        return {
            from: prevRange.from,
            to: prevRange.to,
            group_by: filters.groupBy,
        };
    }, [filters]);

    const { data, isLoading, isError } = useReportsSummary(queryFilters);
    const { data: previousData, isLoading: isPreviousLoading } = useReportsSummary(
        previousFilters ?? queryFilters,
    );

    const handleExport = () => {
        if (!data) {
            return;
        }

        downloadCsv(`reportes-resumen-${filters.from}-${filters.to}`, [
            {
                title: 'KPIs',
                headers: ['Indicador', 'Valor'],
                rows: kpiDefinitions.map((kpi) => [
                    kpi.label,
                    formatValue(kpi.key, data.kpis?.[kpi.key]),
                ]),
            },
            {
                title: 'Serie temporal',
                headers: ['Periodo', 'Ventas brutas', 'Cantidad', 'Ticket promedio'],
                rows: (data.series ?? []).map((point) => [
                    point.period,
                    point.gross_sales,
                    point.sales_count,
                    point.avg_ticket,
                ]),
            },
            {
                title: 'Pagos',
                headers: ['Método', 'Total', 'Pagos', 'Ventas'],
                rows: (data.payments_breakdown ?? []).map((row) => [
                    row.method_label,
                    row.amount_total,
                    row.payments_count,
                    row.sales_count,
                ]),
            },
            {
                title: 'Productos destacados',
                headers: ['Producto', 'Cantidad', 'Total'],
                rows: (data.top_products ?? []).map((row) => [row.name, row.quantity, row.amount_total]),
            },
        ]);
    };

    const rangeLabel = formatRangeLabel(
        data?.range?.from ?? filters.from,
        data?.range?.to ?? filters.to,
    );

    const trendSeries = useMemo(
        () =>
            fillMissingPeriods({
                from: filters.from,
                to: filters.to,
                groupBy: filters.groupBy,
                series: data?.series ?? [],
            }),
        [data?.series, filters.from, filters.to, filters.groupBy],
    );

    const latestGrossSales = trendSeries.at(-1)?.gross_sales ?? '0';
    const trendIsEmpty = !trendSeries.some((point) => toNumber(point.gross_sales) > 0);
    const groupLabel = formatGroupByLabel(filters.groupBy);

    const paymentsBreakdown = data?.payments_breakdown ?? [];
    const totalPayments = paymentsBreakdown.reduce((sum, row) => sum + toNumber(row.amount_total), 0);
    const paymentsSubtitle = rangeLabel;
    const paymentsIsEmpty = !paymentsBreakdown.length || totalPayments === 0;
    const shouldRenderSummary = isLoading || Boolean(data);
    const showStockAlerts = canViewStock && hasInventoryFeature;
    const supplementalGridClass = showStockAlerts ? 'lg:grid-cols-2' : 'lg:grid-cols-1';
    const summarySeries = trendSeries;
    const metricsLoading = isLoading || isPreviousLoading;

    const metricMap = useMemo(
        () => buildMetricCards(metricDefinitions, data, previousData),
        [data, previousData],
    );

    const insights = useMemo(
        () =>
            buildInsights({
                current: data,
                previous: previousData,
                trend: trendSeries,
                payments: paymentsBreakdown,
                totalPayments,
            }),
        [data, previousData, trendSeries, paymentsBreakdown, totalPayments],
    );

    return (
        <div className="space-y-6">
            <div className="mb-4">
                <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Gestión Comercial</p>
                <h1 className="text-3xl font-bold text-slate-900">Reportes</h1>
            </div>

            <ReportsFilters
                value={filters}
                onChange={setFilters}
                showGroupBy
                showStatus
                showPaymentMethod
            />

            <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                    <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Resumen</p>
                    <h2 className="text-2xl font-semibold text-slate-900">Actividad del periodo</h2>
                </div>
                <button
                    type="button"
                    onClick={handleExport}
                    className="inline-flex items-center gap-2 rounded-full border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-400 hover:text-slate-900"
                >
                    Exportar CSV
                </button>
            </div>

            {isError && (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-rose-700">
                    No pudimos cargar los reportes. Probá nuevamente.
                </div>
            )}
            <div className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                    {metricDefinitions.map((definition) => {
                        const metric = metricMap[definition.key];
                        return (
                            <MetricCard
                                key={definition.key}
                                title={definition.title}
                                value={metric?.value ?? '—'}
                                deltaPct={metric?.deltaPct ?? null}
                                tone={metric?.tone ?? 'neutral'}
                                loading={metricsLoading}
                            />
                        );
                    })}
                </div>
                <InsightsRow insights={insights} loading={metricsLoading && !insights.length} />
            </div>

            {shouldRenderSummary && (
                <>
                    <div className="space-y-6">
                        <div className="grid gap-4 lg:grid-cols-3">
                            <div className="space-y-4 lg:col-span-2">
                                <ChartCard
                                    title="Tendencia de ventas brutas"
                                    totalValue={latestGrossSales}
                                    subtitle={rangeLabel}
                                    loading={isLoading}
                                    isEmpty={trendIsEmpty}
                                    height={360}
                                    rightSlot={
                                        groupLabel ? (
                                            <span className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
                                                {groupLabel}
                                            </span>
                                        ) : undefined
                                    }
                                >
                                    <SalesTrendChart data={trendSeries} />
                                </ChartCard>

                                <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                                    <p className="text-sm font-medium text-slate-500">Detalle del período</p>
                                    {summarySeries.length ? (
                                        <table className="mt-6 w-full text-sm">
                                            <thead>
                                                <tr className="text-left text-slate-500">
                                                    <th className="py-2 font-medium">Periodo</th>
                                                    <th className="py-2 font-medium">Ventas brutas</th>
                                                    <th className="py-2 font-medium">Cantidad</th>
                                                    <th className="py-2 font-medium">Ticket promedio</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {summarySeries.map((point) => (
                                                    <tr
                                                        key={point.period}
                                                        className="border-t border-slate-100 text-slate-700"
                                                    >
                                                        <td className="py-2">{point.period}</td>
                                                        <td className="py-2">{formatCurrency(point.gross_sales)}</td>
                                                        <td className="py-2">{formatNumber(point.sales_count)}</td>
                                                        <td className="py-2">{formatCurrency(point.avg_ticket)}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    ) : (
                                        <div className="mt-6">
                                            <EmptyState label="Sin datos en este período" />
                                        </div>
                                    )}
                                </div>
                            </div>

                            <div className="space-y-4">
                                <ChartCard
                                    title="Cobros por medio"
                                    totalValue={totalPayments}
                                    subtitle={paymentsSubtitle}
                                    loading={isLoading}
                                    isEmpty={paymentsIsEmpty}
                                    emptyText="Sin cobros registrados en este período"
                                    height={360}
                                >
                                    <PaymentsDonutChart data={paymentsBreakdown} />
                                </ChartCard>
                            </div>
                        </div>
                    </div>
                    <div className={`grid gap-4 ${supplementalGridClass}`}>
                        <TopProductsWidget filters={queryFilters} />
                        {showStockAlerts && <StockAlertsWidget />}
                    </div>
                </>
            )}

            {!isLoading && !data && !isError && (
                <div className="rounded-3xl border border-slate-200 bg-white/80 p-8 text-center text-slate-500">
                    No hay datos para el rango seleccionado.
                </div>
            )}
        </div>
    );
}

function formatValue(key: KpiKey, value?: string | number | null) {
    if (value === undefined || value === null) {
        return '—';
    }
    switch (key) {
        case 'sales_count':
        case 'units_sold':
        case 'cancellations_count':
            return formatNumber(value);
        default:
            return formatCurrency(value);
    }
}

function formatRangeLabel(from?: string, to?: string) {
    if (!from || !to) {
        return undefined;
    }
    return `${formatDateShort(from)} – ${formatDateShort(to)}`;
}

function formatGroupByLabel(groupBy?: ReportsFiltersValue['groupBy']) {
    switch (groupBy) {
        case 'month':
            return 'Mensual';
        case 'week':
            return 'Semanal';
        case 'day':
            return 'Diario';
        default:
            return undefined;
    }
}

type MetricView = {
    key: string;
    value: string;
    deltaPct: number | null;
    tone: ReturnType<typeof getToneFromDelta>;
};

function buildMetricCards(
    definitions: MetricDefinition[],
    current?: ReportSummaryResponse,
    previous?: ReportSummaryResponse,
) {
    return definitions.reduce<Record<string, MetricView>>((acc, definition) => {
        const currentRaw = definition.getValue(current);
        const previousRaw = definition.getValue(previous);
        const currentNumeric = normalizeMetricValue(currentRaw);
        const previousNumeric = normalizeMetricValue(previousRaw);
        const deltaPct = calculateDeltaPct(currentNumeric, previousNumeric);
        acc[definition.key] = {
            key: definition.key,
            value: formatMetricValue(definition, currentRaw),
            deltaPct,
            tone: getToneFromDelta(deltaPct),
        };
        return acc;
    }, {});
}

function formatMetricValue(definition: MetricDefinition, value?: string | number | null): string {
    if (value === undefined || value === null || value === '') {
        return '—';
    }
    if (definition.type === 'currency') {
        return formatCurrency(value);
    }
    return formatNumber(value);
}

function normalizeMetricValue(value?: string | number | null): number | null {
    if (value === undefined || value === null || value === '') {
        return null;
    }
    if (typeof value === 'number') {
        return value;
    }
    return toNumber(value);
}

type InsightParams = {
    current?: ReportSummaryResponse;
    previous?: ReportSummaryResponse;
    trend: TrendPoint[];
    payments: PaymentBreakdownRow[];
    totalPayments: number;
};

function buildInsights({
    current,
    previous,
    trend,
    payments,
    totalPayments,
}: InsightParams): Insight[] {
    const insights: Insight[] = [];

    const salesDelta = calculateDeltaPct(
        toNumber(current?.kpis?.gross_sales_total),
        toNumber(previous?.kpis?.gross_sales_total),
    );
    if (salesDelta !== null) {
        insights.push({
            id: 'sales-delta',
            text: `Ventas ${salesDelta >= 0 ? 'subieron' : 'bajaron'} ${formatDeltaLabel(salesDelta)} vs período anterior`,
            tone: getToneFromDelta(salesDelta),
        });
    }

    const ticketDelta = calculateDeltaPct(
        toNumber(current?.kpis?.avg_ticket),
        toNumber(previous?.kpis?.avg_ticket),
    );
    if (ticketDelta !== null) {
        insights.push({
            id: 'ticket-delta',
            text: `Ticket promedio ${ticketDelta >= 0 ? 'subió' : 'bajó'} ${formatDeltaLabel(ticketDelta)} vs período anterior`,
            tone: getToneFromDelta(ticketDelta),
        });
    }

    if (payments.length && totalPayments > 0) {
        const topPayment = payments.reduce<{ row: PaymentBreakdownRow | null; amount: number }>(
            (acc, row) => {
                const amount = toNumber(row.amount_total);
                if (!acc.row || amount > acc.amount) {
                    return { row, amount };
                }
                return acc;
            },
            { row: null, amount: 0 },
        );
        if (topPayment.row) {
            const share = (topPayment.amount / totalPayments) * 100;
            insights.push({
                id: 'top-payment',
                text: `Medio principal: ${topPayment.row.method_label} (${share.toFixed(1)}%)`,
                tone: 'neutral',
            });
        }
    }

    const bestDay = trend.reduce<{ point: TrendPoint | null; amount: number }>(
        (acc, point) => {
            const amount = toNumber(point.gross_sales);
            if (!acc.point || amount > acc.amount) {
                return { point, amount };
            }
            return acc;
        },
        { point: null, amount: 0 },
    );

    if (bestDay.point && bestDay.amount > 0) {
        insights.push({
            id: 'best-day',
            text: `Mejor día: ${formatDateLong(bestDay.point.period)} con ${formatCurrency(bestDay.point.gross_sales)}`,
            tone: 'positive',
        });
    }

    return insights;
}

function getPreviousRange(from: string, to: string) {
    const fromDate = new Date(from);
    const toDate = new Date(to);
    const daysDiff = Math.max(1, Math.round((toDate.getTime() - fromDate.getTime()) / DAY_IN_MS) + 1);
    const previousTo = new Date(fromDate);
    previousTo.setDate(previousTo.getDate() - 1);
    const previousFrom = new Date(previousTo);
    previousFrom.setDate(previousFrom.getDate() - daysDiff + 1);
    return {
        from: dateString(previousFrom),
        to: dateString(previousTo),
    };
}

function getRangeForPreset(key: string) {
    const now = new Date();
    switch (key) {
        case 'today':
            return { from: dateString(now), to: dateString(now) };
        case 'yesterday': {
            const date = new Date(now);
            date.setDate(date.getDate() - 1);
            return { from: dateString(date), to: dateString(date) };
        }
        case 'last30': {
            const to = new Date(now);
            const from = new Date(now);
            from.setDate(from.getDate() - 29);
            return { from: dateString(from), to: dateString(to) };
        }
        case 'mtd': {
            const from = new Date(now.getFullYear(), now.getMonth(), 1);
            return { from: dateString(from), to: dateString(now) };
        }
        case 'last_month': {
            const from = new Date(now.getFullYear(), now.getMonth() - 1, 1);
            const to = new Date(now.getFullYear(), now.getMonth(), 0);
            return { from: dateString(from), to: dateString(to) };
        }
        case 'last7':
        default: {
            const to = new Date(now);
            const from = new Date(now);
            from.setDate(from.getDate() - 6);
            return { from: dateString(from), to: dateString(to) };
        }
    }
}

function getDefaultRange() {
    return getRangeForPreset('last7');
}

function dateString(date: Date) {
    return date.toISOString().slice(0, 10);
}

function EmptyState({ label }: { label: string }) {
    return <p className="text-center text-sm text-slate-400">{label}</p>;
}
