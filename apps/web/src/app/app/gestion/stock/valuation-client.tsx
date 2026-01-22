"use client";

import { useEffect, useMemo, useState } from 'react';

import { useInventoryValuation } from '@/features/gestion/hooks';
import type { InventoryValuationFilters } from '@/features/gestion/types';

const statusOptions = [
    { value: '', label: 'Todos los estados' },
    { value: 'ok', label: 'En orden' },
    { value: 'low', label: 'Stock bajo' },
    { value: 'out', label: 'Sin stock' },
];

const sortOptions = [
    { value: 'sale_value_desc', label: 'Mayor valor a precio' },
    { value: 'profit_desc', label: 'Mayor ganancia potencial' },
    { value: 'qty_desc', label: 'Mayor cantidad disponible' },
    { value: 'name_asc', label: 'Nombre (A-Z)' },
];

const activeOptions = [
    { value: 'true', label: 'Solo activos' },
    { value: 'false', label: 'Solo inactivos' },
    { value: 'all', label: 'Todos' },
];

const statusStyles: Record<string, string> = {
    ok: 'bg-emerald-100 text-emerald-700',
    low: 'bg-amber-100 text-amber-700',
    out: 'bg-rose-100 text-rose-700',
};

const statusLabels: Record<string, string> = {
    ok: 'En orden',
    low: 'Stock bajo',
    out: 'Sin stock',
};

function formatCurrency(value?: string | number | null) {
    if (value === null || value === undefined) {
        return '—';
    }
    const numeric = typeof value === 'number' ? value : Number(value);
    if (Number.isNaN(numeric)) {
        return '—';
    }
    return new Intl.NumberFormat('es-AR', {
        style: 'currency',
        currency: 'ARS',
        maximumFractionDigits: 2,
    }).format(numeric);
}

function formatNumber(value?: string | number | null) {
    if (value === null || value === undefined) {
        return '0';
    }
    const numeric = typeof value === 'number' ? value : Number(value);
    if (Number.isNaN(numeric)) {
        return '0';
    }
    return numeric.toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

function formatMargin(value?: string | number | null) {
    if (value === null || value === undefined) {
        return '—';
    }
    const numeric = typeof value === 'number' ? value : Number(value);
    if (Number.isNaN(numeric)) {
        return '—';
    }
    return `${(numeric * 100).toFixed(1)}%`;
}

type StockValuationClientProps = {
    canViewCost: boolean;
};

export function StockValuationClient({ canViewCost }: StockValuationClientProps) {
    const [filters, setFilters] = useState<InventoryValuationFilters>({
        search: '',
        status: '',
        sort: 'sale_value_desc',
        onlyInStock: true,
        active: 'true',
    });

    const valuationQuery = useInventoryValuation(filters);
    const data = valuationQuery.data;
    const items = data?.items ?? [];
    const totals = data?.totals;
    const itemsCount = totals?.items_count ?? 0;
    const availableSortOptions = canViewCost ? sortOptions : sortOptions.filter((option) => option.value !== 'profit_desc');

    useEffect(() => {
        if (!canViewCost && filters.sort === 'profit_desc') {
            setFilters((prev) => ({ ...prev, sort: 'sale_value_desc' }));
        }
    }, [canViewCost, filters.sort]);

    const cards = useMemo(() => {
        const base = [
            { label: 'Valor a precio', value: formatCurrency(totals?.total_sale_value) },
        ];
        if (canViewCost) {
            base.push(
                { label: 'Valor a costo', value: formatCurrency(totals?.total_cost_value) },
                { label: 'Ganancia potencial', value: formatCurrency(totals?.total_potential_profit) },
            );
        }
        return base;
    }, [totals, canViewCost]);

    const handleFilterChange = <K extends keyof InventoryValuationFilters>(key: K, value: InventoryValuationFilters[K]) => {
        setFilters((prev) => ({
            ...prev,
            [key]: value,
        }));
    };

    return (
        <section className="space-y-5">
            <header className="space-y-3">
                <div>
                    <h2 className="text-2xl font-semibold text-slate-900">Valorización del inventario</h2>
                    <p className="text-sm text-slate-500">Proyección potencial si vendés todo tu stock al precio actual.</p>
                </div>
                {!canViewCost && (
                    <p className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
                        Tu rol no permite ver costos ni márgenes. Solo mostramos el valor estimado a precio de venta.
                    </p>
                )}
            </header>
            <div className="grid gap-4 md:grid-cols-3">
                {cards.map((card) => (
                    <article key={card.label} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                        <p className="text-xs uppercase tracking-wide text-slate-400">{card.label}</p>
                        <p className="mt-2 text-3xl font-semibold text-slate-900">{card.value}</p>
                    </article>
                ))}
            </div>
            <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                {valuationQuery.isError ? (
                    <p className="mb-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
                        No pudimos calcular la valorización. Intentá nuevamente.
                    </p>
                ) : null}
                <div className="grid gap-3 md:grid-cols-4">
                    <input
                        type="search"
                        value={filters.search ?? ''}
                        onChange={(event) => handleFilterChange('search', event.target.value)}
                        placeholder="Buscar por nombre o SKU"
                        className="rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none md:col-span-2"
                    />
                    <select
                        value={filters.status ?? ''}
                        onChange={(event) => handleFilterChange('status', event.target.value)}
                        className="rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
                    >
                        {statusOptions.map((option) => (
                            <option key={option.value} value={option.value}>
                                {option.label}
                            </option>
                        ))}
                    </select>
                    <select
                        value={filters.active ?? 'true'}
                        onChange={(event) => handleFilterChange('active', event.target.value as InventoryValuationFilters['active'])}
                        className="rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
                    >
                        {activeOptions.map((option) => (
                            <option key={option.value} value={option.value}>
                                {option.label}
                            </option>
                        ))}
                    </select>
                </div>
                <div className="mt-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <label className="flex items-center gap-2 text-sm text-slate-500">
                        <input
                            type="checkbox"
                            checked={filters.onlyInStock ?? false}
                            onChange={(event) => handleFilterChange('onlyInStock', event.target.checked)}
                            className="size-4 rounded border-slate-300 text-slate-900 focus:ring-slate-500"
                        />
                        Solo con stock disponible
                    </label>
                    <select
                        value={filters.sort ?? 'sale_value_desc'}
                        onChange={(event) => handleFilterChange('sort', event.target.value as InventoryValuationFilters['sort'])}
                        className="rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none md:w-64"
                    >
                        {availableSortOptions.map((option) => (
                            <option key={option.value} value={option.value}>
                                {option.label}
                            </option>
                        ))}
                    </select>
                </div>
                <p className="mt-3 text-xs uppercase tracking-wide text-slate-400">{itemsCount} productos</p>
                <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-100 text-sm">
                        <thead>
                            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                                <th className="px-3 py-2">Producto</th>
                                <th className="px-3 py-2">Stock</th>
                                <th className="px-3 py-2">Precio</th>
                                <th className="px-3 py-2">Valor a precio</th>
                                {canViewCost ? <th className="px-3 py-2">Costo</th> : null}
                                {canViewCost ? <th className="px-3 py-2">Valor a costo</th> : null}
                                {canViewCost ? <th className="px-3 py-2">Ganancia potencial</th> : null}
                                {canViewCost ? <th className="px-3 py-2">Margen</th> : null}
                                <th className="px-3 py-2">Estado</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {valuationQuery.isLoading && (
                                <tr>
                                    <td colSpan={canViewCost ? 9 : 5} className="px-3 py-6 text-center text-slate-500">
                                        Calculando valorización...
                                    </td>
                                </tr>
                            )}
                            {!valuationQuery.isLoading && items.length === 0 && (
                                <tr>
                                    <td colSpan={canViewCost ? 9 : 5} className="px-3 py-6 text-center text-slate-500">
                                        No encontramos productos que coincidan con los filtros.
                                    </td>
                                </tr>
                            )}
                            {items.map((item) => (
                                <tr key={item.product_id}>
                                    <td className="px-3 py-3">
                                        <p className="font-medium text-slate-900">{item.name}</p>
                                        <p className="text-xs text-slate-400">SKU {item.sku || '—'}</p>
                                    </td>
                                    <td className="px-3 py-3 font-semibold text-slate-900">{formatNumber(item.qty)}</td>
                                    <td className="px-3 py-3 text-slate-600">{formatCurrency(item.price)}</td>
                                    <td className="px-3 py-3 font-semibold text-slate-900">{formatCurrency(item.sale_value)}</td>
                                    {canViewCost ? <td className="px-3 py-3 text-slate-600">{formatCurrency(item.cost)}</td> : null}
                                    {canViewCost ? <td className="px-3 py-3 font-semibold text-slate-900">{formatCurrency(item.cost_value)}</td> : null}
                                    {canViewCost ? <td className="px-3 py-3 font-semibold text-emerald-700">{formatCurrency(item.potential_profit)}</td> : null}
                                    {canViewCost ? <td className="px-3 py-3 text-slate-600">{formatMargin(item.margin_pct)}</td> : null}
                                    <td className="px-3 py-3">
                                        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusStyles[item.status] ?? 'bg-slate-100 text-slate-600'}`}>
                                            {statusLabels[item.status] ?? item.status}
                                        </span>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </section>
    );
}
