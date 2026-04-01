'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';

import { formatDateShort } from '@/components/reports/utils/format';
import { useTopProductsLeaderboard } from '@/features/reports/hooks';
import type { ReportsFilters, TopProductLeaderboardItem } from '@/features/reports/types';
import { formatARS, formatNumber } from '@/lib/format';
import { HorizontalRankChart } from '@/lib/charts';

export type MetricOption = 'amount' | 'units';

type TopProductsWidgetProps = {
    filters: ReportsFilters;
    limit?: number;
};

export function TopProductsWidget({ filters, limit = 10 }: TopProductsWidgetProps) {
    const [metric, setMetric] = useState<MetricOption>('amount');
    const { data, isLoading } = useTopProductsLeaderboard(filters, metric, limit);
    const items = data?.items ?? [];
    const visibleItems = useMemo(() => items.slice(0, 5), [items]);
    const rangeLabel = data?.range ? `${formatDateShort(data.range.from)} – ${formatDateShort(data.range.to)}` : undefined;

    return (
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <p className="text-sm font-medium text-slate-500">Top productos vendidos</p>
                    {rangeLabel && <p className="text-xs text-slate-400">{rangeLabel}</p>}
                </div>
                <MetricToggle metric={metric} onChange={setMetric} />
            </div>

            <TopProductsList items={visibleItems} metric={metric} loading={isLoading} />

            <div className="mt-5 flex items-center justify-between text-sm text-slate-500">
                <Link
                    href="/app/gestion/reportes/productos"
                    className="font-semibold text-slate-900 transition hover:text-slate-600"
                >
                    Ver más
                </Link>
                <span className="text-xs">
                    {visibleItems.length ? `Top ${visibleItems.length} de ${Math.min(items.length, limit) || 0}` : 'Sin resultados'}
                </span>
            </div>
        </div>
    );
}

type MetricToggleProps = {
    metric: MetricOption;
    onChange: (metric: MetricOption) => void;
};

function MetricToggle({ metric, onChange }: MetricToggleProps) {
    const options: Array<{ key: MetricOption; label: string }> = [
        { key: 'amount', label: 'Por ventas $' },
        { key: 'units', label: 'Por unidades' },
    ];
    return (
        <div className="inline-flex rounded-full bg-slate-100 p-1 text-xs font-semibold">
            {options.map((option) => (
                <button
                    key={option.key}
                    type="button"
                    onClick={() => onChange(option.key)}
                    className={`rounded-full px-3 py-1 transition ${option.key === metric ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
                    aria-pressed={option.key === metric}
                >
                    {option.label}
                </button>
            ))}
        </div>
    );
}

type TopProductsListProps = {
    items: TopProductLeaderboardItem[];
    metric: MetricOption;
    loading: boolean;
};

export function TopProductsList({ items, metric, loading }: TopProductsListProps) {
    const chartItems = useMemo(
        () => items.map(item => ({
            name: item.name,
            value: metric === 'amount' ? Number(item.amount_total) || 0 : Number(item.units) || 0,
        })),
        [items, metric],
    );

    if (loading) {
        return (
            <ul className="mt-4 space-y-3">
                {Array.from({ length: 5 }).map((_, index) => (
                    <li key={`skeleton-${index}`} className="h-16 animate-pulse rounded-2xl bg-slate-100/80" />
                ))}
            </ul>
        );
    }

    if (!items.length) {
        return (
            <div className="mt-4 rounded-2xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-400">
                No hay ventas en este período
            </div>
        );
    }

    const fmtLabel = metric === 'amount'
        ? (v: number) => formatARS(v)
        : (v: number) => `${formatNumber(v)} u`;

    return (
        <div className="mt-4">
            <HorizontalRankChart
                items={chartItems}
                formatLabel={fmtLabel}
                formatTooltip={(name, value, idx) => {
                    const item = items[idx];
                    return `<div style="font-weight:600;margin-bottom:4px">${name}</div>
                        <div style="font-family:ui-monospace,monospace;font-weight:600">${formatARS(item?.amount_total)}</div>
                        <div style="font-size:12px;color:#94a3b8;margin-top:2px">${formatNumber(item?.units)} u · ${item?.share_pct}%</div>`;
                }}
                color={metric === 'amount' ? '#0f172a' : '#0ea5e9'}
            />
        </div>
    );
}
