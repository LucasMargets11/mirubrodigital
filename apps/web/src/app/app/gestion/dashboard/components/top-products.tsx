"use client";

import Link from 'next/link';

import { useTopSellingProducts } from '@/features/gestion/hooks';
import { formatCurrency, formatNumber } from '@/lib/format';

type TopProductsProps = {
    canViewSales: boolean;
    salesEnabled: boolean;
};

export function TopProducts({ canViewSales, salesEnabled }: TopProductsProps) {
    const enabled = canViewSales && salesEnabled;
    const topQuery = useTopSellingProducts('7d', 5, enabled);
    const items = enabled ? topQuery.data?.items ?? [] : [];
    const maxQuantity = items.reduce((acc, item) => Math.max(acc, Number(item.total_qty)), 0);

    return (
        <section className="space-y-4 rounded-3xl border border-slate-100 bg-white p-5 shadow-sm">
            <header className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                <div>
                    <h2 className="text-lg font-semibold text-slate-900">Productos calientes</h2>
                    <p className="text-sm text-slate-500">Top ventas de los últimos 7 días.</p>
                </div>
                {enabled ? (
                    <Link href="/app/gestion/reportes/ventas" className="text-sm font-semibold text-slate-600 hover:text-slate-900">
                        Ir a reportes →
                    </Link>
                ) : null}
            </header>

            {!enabled ? (
                <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
                    Activá el módulo de ventas o pedí permiso para visualizar este ranking.
                </div>
            ) : (
                <div className="space-y-3">
                    {topQuery.isLoading ? <ProductSkeleton /> : null}
                    {!topQuery.isLoading && items.length === 0 ? (
                        <p className="text-sm text-slate-500">Aún no se registran ventas en el período.</p>
                    ) : null}
                    {items.map((item, index) => {
                        const quantity = Number(item.total_qty);
                        const ratio = maxQuantity ? Math.round((quantity / maxQuantity) * 100) : 0;
                        return (
                            <div key={`${item.product_id ?? 'snapshot'}-${index}`} className="rounded-2xl border border-slate-100 p-3">
                                <div className="flex items-center justify-between gap-2">
                                    <div className="flex items-center gap-3">
                                        <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">#{index + 1}</span>
                                        <div>
                                            <p className="text-sm font-semibold text-slate-900">{item.name || 'Producto sin nombre'}</p>
                                            <p className="text-xs text-slate-500">
                                                {formatNumber(item.total_qty)} uds · {formatCurrency(item.total_sales)}
                                            </p>
                                        </div>
                                    </div>
                                    <TrendArrow trend={ratio} />
                                </div>
                                <div className="mt-3 h-2 rounded-full bg-slate-100">
                                    <div
                                        className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-blue-500"
                                        style={{ width: `${ratio}%` }}
                                    />
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </section>
    );
}

function TrendArrow({ trend }: { trend: number }) {
    let label = 'Estable';
    let color = 'text-slate-500';
    let symbol = '→';

    if (trend >= 70) {
        label = '🔥 Alta rotación';
        color = 'text-emerald-600';
        symbol = '↑';
    } else if (trend <= 25) {
        label = '⚠️ Lentitud';
        color = 'text-amber-600';
        symbol = '↓';
    }

    return (
        <span className={`text-xs font-semibold ${color}`}>
            {symbol} {label}
        </span>
    );
}

function ProductSkeleton() {
    return (
        <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, idx) => (
                <div key={idx} className="animate-pulse rounded-2xl border border-slate-100 p-3">
                    <div className="mb-2 h-4 w-1/2 rounded-full bg-slate-200" />
                    <div className="h-2 w-full rounded-full bg-slate-100" />
                </div>
            ))}
        </div>
    );
}
