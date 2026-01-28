'use client';

import { useEffect, useMemo, useState } from 'react';

import { downloadCsv } from '@/lib/csv';
import { formatCurrency, formatNumber } from '@/lib/format';
import { useReportsProducts } from '@/features/reports/hooks';

import { ReportsFilters, type ReportsFiltersValue } from '@/modules/reports/components/filters';
import { ReportsPagination } from '@/modules/reports/components/pagination';

const defaultRange = getDefaultRange();

export function ReportsProductsClient() {
    const [filters, setFilters] = useState<ReportsFiltersValue>({
        preset: 'last30',
        from: defaultRange.from,
        to: defaultRange.to,
    });
    const [limit] = useState(50);
    const [offset, setOffset] = useState(0);
    const [searchInput, setSearchInput] = useState('');
    const [search, setSearch] = useState('');

    useEffect(() => {
        setOffset(0);
    }, [filters, search]);

    const queryFilters = useMemo(
        () => ({
            from: filters.from,
            to: filters.to,
            status: filters.status,
            payment_method: filters.paymentMethod,
            user_id: filters.userId,
            q: search || undefined,
            limit,
            offset,
        }),
        [filters, search, limit, offset],
    );

    const { data, isLoading, isError } = useReportsProducts(queryFilters);

    const handleExport = () => {
        if (!data?.results?.length) {
            return;
        }
        downloadCsv(`reportes-productos-${filters.from}-${filters.to}`, [
            {
                title: 'Totales',
                headers: ['Productos', 'Unidades', 'Ventas', 'Precio promedio'],
                rows: [
                    [
                        data.totals?.products_count ?? 0,
                        data.totals?.units ?? '0.00',
                        data.totals?.gross_sales ?? '0.00',
                        data.totals?.avg_price ?? '0.00',
                    ],
                ],
            },
            {
                title: 'Detalle',
                headers: ['Producto', 'SKU', 'Unidades', 'Ventas', 'Participación', 'Operaciones'],
                rows: data.results.map((row) => [
                    row.name,
                    row.sku || '—',
                    row.quantity,
                    row.amount_total,
                    `${formatShare(row.share)}`,
                    row.sales_count,
                ]),
            },
        ]);
    };

    const handleSearchSubmit = (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        setSearch(searchInput.trim());
    };

    return (
        <div className="space-y-6">
            <ReportsFilters value={filters} onChange={setFilters} showStatus showPaymentMethod showUser />

            <section className="rounded-3xl border border-slate-200 bg-white/80 p-4 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Productos</p>
                        <h2 className="text-2xl font-semibold text-slate-900">Mix de ventas</h2>
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                        <form onSubmit={handleSearchSubmit} className="flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1.5">
                            <input
                                type="search"
                                value={searchInput}
                                onChange={(event) => setSearchInput(event.target.value)}
                                placeholder="Buscar producto o SKU"
                                className="w-44 bg-transparent text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none"
                            />
                            <button type="submit" className="text-sm font-medium text-slate-600">
                                Buscar
                            </button>
                        </form>
                        <button
                            type="button"
                            onClick={handleExport}
                            className="inline-flex items-center gap-2 rounded-full border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-400 hover:text-slate-900"
                        >
                            Exportar CSV
                        </button>
                    </div>
                </div>

                {isError && (
                    <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                        Error al cargar productos.
                    </div>
                )}

                <div className="mt-6 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                    <KpiCard label="Productos" value={formatNumber(data?.totals?.products_count ?? 0)} />
                    <KpiCard label="Unidades" value={formatNumber(data?.totals?.units ?? '0.00')} />
                    <KpiCard label="Ventas" value={formatCurrency(data?.totals?.gross_sales ?? '0')} />
                    <KpiCard label="Precio promedio" value={formatCurrency(data?.totals?.avg_price ?? '0')} />
                </div>

                <div className="mt-8 overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-left text-slate-500">
                                <th className="px-2 py-2 font-medium">Producto</th>
                                <th className="px-2 py-2 font-medium">SKU</th>
                                <th className="px-2 py-2 font-medium text-right">Ventas</th>
                                <th className="px-2 py-2 font-medium text-right">Unidades</th>
                                <th className="px-2 py-2 font-medium">Participación</th>
                                <th className="px-2 py-2 font-medium text-right">Operaciones</th>
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading && (
                                <tr>
                                    <td colSpan={6} className="px-2 py-6 text-center text-slate-500">
                                        Cargando productos...
                                    </td>
                                </tr>
                            )}
                            {!isLoading && !data?.results?.length && (
                                <tr>
                                    <td colSpan={6} className="px-2 py-6 text-center text-slate-500">
                                        No hay ventas para el rango seleccionado.
                                    </td>
                                </tr>
                            )}
                            {(data?.results ?? []).map((row) => {
                                const shareValue = Number(row.share ?? '0');
                                return (
                                    <tr key={`${row.product_id ?? 'custom'}-${row.name}`} className="border-t border-slate-100 text-slate-700">
                                        <td className="px-2 py-3">
                                            <p className="font-semibold text-slate-900">{row.name}</p>
                                        </td>
                                        <td className="px-2 py-3 text-slate-500">{row.sku || '—'}</td>
                                        <td className="px-2 py-3 text-right font-semibold">{formatCurrency(row.amount_total)}</td>
                                        <td className="px-2 py-3 text-right">{formatNumber(row.quantity)}</td>
                                        <td className="px-2 py-3">
                                            <div className="flex items-center gap-3">
                                                <span className="font-semibold text-slate-900">{formatShare(row.share)}</span>
                                                <div className="h-2 w-32 rounded-full bg-slate-100">
                                                    <div
                                                        className="h-full rounded-full bg-slate-900"
                                                        style={{ width: `${Math.max(0, Math.min(100, shareValue))}%` }}
                                                    />
                                                </div>
                                            </div>
                                        </td>
                                        <td className="px-2 py-3 text-right">{formatNumber(row.sales_count)}</td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>

                <div className="mt-4">
                    <ReportsPagination
                        count={data?.count ?? 0}
                        limit={limit}
                        offset={offset}
                        onChange={setOffset}
                        disabled={isLoading}
                    />
                </div>
            </section>
        </div>
    );
}

function getDefaultRange() {
    const to = new Date();
    const from = new Date();
    from.setDate(to.getDate() - 29);
    return { from: toIso(from), to: toIso(to) };
}

function toIso(date: Date) {
    return date.toISOString().slice(0, 10);
}

function KpiCard({ label, value }: { label: string; value: string }) {
    return (
        <div className="rounded-3xl border border-slate-200 bg-gradient-to-br from-white to-slate-50 p-4 shadow-sm">
            <p className="text-sm font-medium text-slate-500">{label}</p>
            <p className="mt-2 text-2xl font-semibold text-slate-900">{value}</p>
        </div>
    );
}

function formatShare(value?: string | number | null) {
    if (value === null || value === undefined) {
        return '0%';
    }
    const numeric = Number(value);
    if (Number.isNaN(numeric)) {
        return '0%';
    }
    return `${numeric.toFixed(2)}%`;
}
