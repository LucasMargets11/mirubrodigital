'use client';

import Link from 'next/link';
import type { ReactNode } from 'react';

import { useStockAlerts } from '@/features/reports/hooks';
import type { StockAlertRow, StockAlertsResponse } from '@/features/reports/types';
import { getStockStatusIcon, getStockStatusTone, humanizeStockStatus } from '@/features/reports/utils/stock-alerts';
import { formatNumber } from '@/lib/format';

type StockAlertsWidgetProps = {
    limit?: number;
};

export function StockAlertsWidget({ limit = 6 }: StockAlertsWidgetProps) {
    const { data, isLoading } = useStockAlerts(limit);
    return (
        <StockAlertsPanel
            data={data}
            loading={isLoading}
            cta={
                <Link href="/app/gestion/stock" className="text-sm font-semibold text-slate-900 transition hover:text-slate-600">
                    Ver stock
                </Link>
            }
        />
    );
}

type StockAlertsPanelProps = {
    data?: StockAlertsResponse;
    loading: boolean;
    cta?: ReactNode;
};

export function StockAlertsPanel({ data, loading, cta }: StockAlertsPanelProps) {
    const items = data?.items ?? [];
    return (
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-slate-500">Alertas de stock</p>
                <span className="text-xs text-slate-400">Inventario crítico</span>
            </div>

            <div className="mt-4 flex flex-wrap gap-3">
                <AlertBadge tone="danger" icon="⚠" label="Sin stock" value={data?.out_of_stock_count ?? 0} loading={loading} />
                <AlertBadge tone="warning" icon="!" label="Bajo stock" value={data?.low_stock_count ?? 0} loading={loading} />
            </div>

            <StockAlertsList items={items} loading={loading} />

            <div className="mt-6 flex justify-end">
                {cta ?? (
                    <Link href="/app/gestion/stock" className="text-sm font-semibold text-slate-900 transition hover:text-slate-600">
                        Ver stock
                    </Link>
                )}
            </div>
        </div>
    );
}

type AlertBadgeProps = {
    tone: 'danger' | 'warning';
    icon: string;
    label: string;
    value: number;
    loading: boolean;
};

function AlertBadge({ tone, icon, label, value, loading }: AlertBadgeProps) {
    const toneClasses = tone === 'danger' ? 'bg-rose-50 text-rose-700' : 'bg-amber-50 text-amber-700';
    if (loading) {
        const skeletonClass = tone === 'danger' ? 'bg-rose-100/60' : 'bg-amber-100/60';
        return <div className={`h-12 w-32 animate-pulse rounded-2xl ${skeletonClass}`} />;
    }
    return (
        <div className={`inline-flex items-center gap-2 rounded-2xl px-4 py-2 text-sm font-semibold ${toneClasses}`}>
            <span>{icon}</span>
            <span>{label}:</span>
            <span>{value}</span>
        </div>
    );
}

type StockAlertsListProps = {
    items: StockAlertRow[];
    loading: boolean;
};

function StockAlertsList({ items, loading }: StockAlertsListProps) {
    if (loading) {
        return (
            <ul className="mt-5 space-y-3">
                {Array.from({ length: 4 }).map((_, index) => (
                    <li key={`stock-skeleton-${index}`} className="h-16 animate-pulse rounded-2xl bg-slate-100/80" />
                ))}
            </ul>
        );
    }

    if (!items.length) {
        return (
            <div className="mt-5 rounded-2xl border border-dashed border-emerald-200 bg-emerald-50/60 p-6 text-center text-sm font-semibold text-emerald-600">
                No hay alertas de stock 🎉
            </div>
        );
    }

    return (
        <ul className="mt-5 space-y-3">
            {items.map((item) => {
                const tone = getStockStatusTone(item.status);
                const icon = getStockStatusIcon(item.status);
                const valueClass = tone === 'danger' ? 'text-rose-600' : 'text-amber-600';
                const chipClass = tone === 'danger' ? 'bg-rose-50 text-rose-700' : 'bg-amber-50 text-amber-700';
                const key = item.product_id ?? `${item.name}-${item.status}`;
                return (
                    <li key={key} className="rounded-2xl border border-slate-100 p-4">
                        <div className="flex items-start justify-between gap-3">
                            <div>
                                <p className="flex items-center gap-2 font-semibold text-slate-900">
                                    <span>{item.name}</span>
                                    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${chipClass}`}>
                                        {icon} {item.status === 'OUT' ? 'Sin stock' : 'Bajo stock'}
                                    </span>
                                </p>
                                <p className="text-xs text-slate-500">{humanizeStockStatus(item.status, item.threshold)}</p>
                            </div>
                            <div className={`text-right text-sm font-semibold ${valueClass}`}>
                                {formatNumber(item.stock)} u
                            </div>
                        </div>
                    </li>
                );
            })}
        </ul>
    );
}
