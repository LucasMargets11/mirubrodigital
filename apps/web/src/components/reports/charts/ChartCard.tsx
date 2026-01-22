'use client';

import { ReactNode } from 'react';

import { formatARS } from '../utils/format';

type ChartCardProps = {
    title: string;
    totalValue?: string | number | null;
    subtitle?: string;
    rightSlot?: ReactNode;
    loading?: boolean;
    isEmpty?: boolean;
    emptyText?: string;
    children: ReactNode;
    height?: number;
};

const DEFAULT_HEIGHT = 280;

export function ChartCard({
    title,
    totalValue,
    subtitle,
    rightSlot,
    loading = false,
    isEmpty = false,
    emptyText = 'Sin datos en este período',
    children,
    height = DEFAULT_HEIGHT,
}: ChartCardProps) {
    const formattedTotal = formatTotalValue(totalValue);
    const showEmpty = !loading && isEmpty;
    const contentStyle = { height };

    return (
        <section className="flex flex-col rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="space-y-2">
                    <p className="text-xs uppercase tracking-[0.3em] text-slate-400">{title}</p>
                    <div className="min-h-[2.5rem]">
                        {loading ? (
                            <div className="h-8 w-40 animate-pulse rounded-full bg-slate-100" />
                        ) : (
                            formattedTotal && <p className="text-2xl font-semibold text-slate-900">{formattedTotal}</p>
                        )}
                    </div>
                    {subtitle && <p className="text-sm text-slate-500">{subtitle}</p>}
                </div>
                {rightSlot && <div className="flex items-start justify-end sm:justify-center">{rightSlot}</div>}
            </header>

            <div className="mt-6">
                {loading ? (
                    <div className="w-full animate-pulse rounded-2xl bg-slate-100" style={contentStyle} />
                ) : showEmpty ? (
                    <div className="flex w-full items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 p-6 text-sm text-slate-500" style={contentStyle}>
                        {emptyText}
                    </div>
                ) : (
                    <div className="w-full" style={contentStyle}>
                        {children}
                    </div>
                )}
            </div>
        </section>
    );
}

function formatTotalValue(value?: string | number | null) {
    if (value === null || value === undefined || value === '') {
        return null;
    }
    return formatARS(value);
}
