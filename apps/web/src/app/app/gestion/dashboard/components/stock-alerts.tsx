"use client";

import Link from 'next/link';

import { useLowStockPreview, useOutOfStockPreview } from '@/features/gestion/hooks';
import type { ProductStock } from '@/features/gestion/types';
import { formatNumber } from '@/lib/format';
import { cn } from '@/lib/utils';

type StockAlertsProps = {
    canView: boolean;
    inventoryEnabled: boolean;
};

export function StockAlerts({ canView, inventoryEnabled }: StockAlertsProps) {
    const enabled = canView && inventoryEnabled;
    const lowStockQuery = useLowStockPreview(5, enabled);
    const outOfStockQuery = useOutOfStockPreview(5, enabled);

    return (
        <section className="space-y-4 rounded-3xl border border-slate-100 bg-white p-5 shadow-sm">
            <header className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                <div>
                    <h2 className="text-lg font-semibold text-slate-900">Alertas de stock</h2>
                    <p className="text-sm text-slate-500">Identificá rápido qué reponer antes que impacte en ventas.</p>
                </div>
                {enabled ? (
                    <Link
                        href="/app/gestion/stock"
                        className="text-sm font-semibold text-slate-600 hover:text-slate-900"
                    >
                        Ver tablero completo →
                    </Link>
                ) : null}
            </header>

            {!enabled ? (
                <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
                    Activá el módulo de inventario o pedí permisos para ver alertas.
                </div>
            ) : (
                <div className="space-y-4">
                    <AlertGroup
                        title="Sin stock"
                        tone="critical"
                        status="out"
                        items={outOfStockQuery.data ?? []}
                        isLoading={outOfStockQuery.isLoading}
                        emptyLabel="Todo abastecido"
                    />
                    <AlertGroup
                        title="Stock bajo"
                        tone="warning"
                        status="low"
                        items={lowStockQuery.data ?? []}
                        isLoading={lowStockQuery.isLoading}
                        emptyLabel="Sin alertas por ahora"
                    />
                </div>
            )}
        </section>
    );
}

type AlertGroupProps = {
    title: string;
    tone: 'critical' | 'warning';
    status: 'low' | 'out';
    items: ProductStock[];
    isLoading: boolean;
    emptyLabel: string;
};

function AlertGroup({ title, tone, status, items, isLoading, emptyLabel }: AlertGroupProps) {
    const bgClass = tone === 'critical' ? 'bg-rose-50 border-rose-100' : 'bg-amber-50 border-amber-100';
    const barClass = tone === 'critical' ? 'from-rose-500 to-rose-600' : 'from-amber-500 to-amber-600';
    const chipClass = tone === 'critical' ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700';

    return (
        <div className={cn('rounded-2xl border p-4', bgClass)}>
            <div className="mb-3 flex items-center justify-between">
                <p className="text-sm font-semibold text-slate-900">{title}</p>
                <Link
                    href={`/app/gestion/stock?status=${status}`}
                    className="text-xs font-semibold text-slate-600 hover:text-slate-900"
                >
                    Ver todos →
                </Link>
            </div>
            <div className="space-y-3">
                {isLoading ? (
                    <SkeletonRow />
                ) : null}
                {!isLoading && items.length === 0 ? (
                    <p className="text-sm text-slate-500">{emptyLabel}</p>
                ) : null}
                {items.map((item) => (
                    <AlertRow key={item.id} item={item} chipClass={chipClass} barClass={barClass} status={status} />
                ))}
            </div>
        </div>
    );
}

type AlertRowProps = {
    item: ProductStock;
    chipClass: string;
    barClass: string;
    status: 'low' | 'out';
};

function AlertRow({ item, chipClass, barClass, status }: AlertRowProps) {
    const qty = Number(item.quantity);
    const min = Number(item.product.stock_min) || 1;
    const ratio = Math.max(0, Math.min(100, Math.round((qty / min) * 100)));
    const productName = item.product.name;

    return (
        <div className="flex flex-col gap-3 rounded-2xl border border-white/60 bg-white/60 p-3 backdrop-blur">
            <div className="flex items-center justify-between gap-2">
                <div className="truncate">
                    <p className="truncate text-sm font-semibold text-slate-900">{productName}</p>
                    <p className="text-xs text-slate-500">Stock: {formatNumber(item.quantity)} · Mín: {formatNumber(item.product.stock_min)}</p>
                </div>
                <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-semibold', chipClass)}>
                    {status === 'out' ? 'Sin stock' : 'Stock bajo'}
                </span>
            </div>
            <div className="flex items-center gap-3">
                <div className="h-2 flex-1 rounded-full bg-slate-100">
                    <div className={cn('h-2 rounded-full bg-gradient-to-r', barClass)} style={{ width: `${ratio}%` }} />
                </div>
                <Link
                    href={`/app/gestion/stock?status=${status}&action=movement&product=${item.product.id}`}
                    className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900"
                    aria-label="Reponer stock"
                >
                    Reponer
                </Link>
            </div>
        </div>
    );
}

function SkeletonRow() {
    return (
        <div className="animate-pulse rounded-2xl border border-white/60 bg-white/60 p-3">
            <div className="mb-2 h-3 w-1/2 rounded-full bg-slate-200" />
            <div className="mb-3 h-2 w-2/3 rounded-full bg-slate-100" />
            <div className="h-2 w-full rounded-full bg-slate-100" />
        </div>
    );
}
