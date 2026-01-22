'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import { downloadCsv } from '@/lib/csv';
import { formatCurrency, formatNumber } from '@/lib/format';
import { useReportsSales } from '@/features/reports/hooks';

import { ReportsFilters, type ReportsFiltersValue } from '../components/reports-filters';
import { ReportsPagination } from '../components/pagination';

const defaultRange = getDefaultRange();

export function ReportsSalesClient() {
    const [filters, setFilters] = useState<ReportsFiltersValue>({
        preset: 'last7',
        from: defaultRange.from,
        to: defaultRange.to,
    });
    const [searchInput, setSearchInput] = useState('');
    const [search, setSearch] = useState('');
    const [limit] = useState(25);
    const [offset, setOffset] = useState(0);

    useEffect(() => {
        setOffset(0);
    }, [filters, search]);

    const queryFilters = useMemo(
        () => ({
            from: filters.from,
            to: filters.to,
            status: filters.status,
            payment_method: filters.paymentMethod,
            method: filters.method,
            user_id: filters.userId,
            register_id: filters.registerId,
            q: search || undefined,
            limit,
            offset,
        }),
        [filters, search, limit, offset],
    );

    const { data, isLoading, isError } = useReportsSales(queryFilters);

    const handleExport = () => {
        if (!data?.results?.length) {
            return;
        }
        downloadCsv(`reportes-ventas-${filters.from}-${filters.to}`, [
            {
                title: 'Ventas',
                headers: ['#', 'Fecha', 'Cliente', 'Estado', 'Método', 'Total', 'Cajero'],
                rows: data.results.map((sale) => [
                    sale.number,
                    formatDate(sale.created_at),
                    sale.customer_name ?? 'Mostrador',
                    sale.status_label,
                    sale.payment_method_label,
                    sale.total,
                    sale.cashier?.name ?? '—',
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
            <ReportsFilters
                value={filters}
                onChange={setFilters}
                showStatus
                showPaymentMethod
                showMethod
                showRegister
                showUser
            />

            <section className="rounded-3xl border border-slate-200 bg-white/80 p-4 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Ventas</p>
                        <h2 className="text-2xl font-semibold text-slate-900">Detalle del periodo</h2>
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                        <form onSubmit={handleSearchSubmit} className="flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1.5">
                            <input
                                type="search"
                                value={searchInput}
                                onChange={(event) => setSearchInput(event.target.value)}
                                placeholder="Buscar cliente, #"
                                className="w-40 bg-transparent text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none"
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
                        Error al cargar ventas.
                    </div>
                )}

                <div className="mt-6 overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-left text-slate-500">
                                <th className="px-2 py-2 font-medium">#</th>
                                <th className="px-2 py-2 font-medium">Fecha</th>
                                <th className="px-2 py-2 font-medium">Cliente</th>
                                <th className="px-2 py-2 font-medium">Estado</th>
                                <th className="px-2 py-2 font-medium">Método</th>
                                <th className="px-2 py-2 font-medium">Pagos</th>
                                <th className="px-2 py-2 font-medium">Total</th>
                                <th className="px-2 py-2 font-medium">Cajero</th>
                                <th className="px-2 py-2" />
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading && (
                                <tr>
                                    <td colSpan={9} className="px-2 py-6 text-center text-slate-500">
                                        Cargando ventas...
                                    </td>
                                </tr>
                            )}
                            {!isLoading && !data?.results?.length && (
                                <tr>
                                    <td colSpan={9} className="px-2 py-6 text-center text-slate-500">
                                        No hay ventas en el rango seleccionado.
                                    </td>
                                </tr>
                            )}
                            {(data?.results ?? []).map((sale) => (
                                <tr key={sale.id} className="border-t border-slate-100 text-slate-700">
                                    <td className="px-2 py-3 font-semibold">#{sale.number}</td>
                                    <td className="px-2 py-3">{formatDate(sale.created_at)}</td>
                                    <td className="px-2 py-3">
                                        <p className="font-medium">{sale.customer_name ?? 'Mostrador'}</p>
                                        <p className="text-xs text-slate-500">{sale.customer?.email ?? 'Sin email'}</p>
                                    </td>
                                    <td className="px-2 py-3">
                                        <StatusBadge status={sale.status} label={sale.status_label} />
                                    </td>
                                    <td className="px-2 py-3">
                                        <p className="font-medium">{sale.payment_method_label}</p>
                                        {sale.items_count && (
                                            <p className="text-xs text-slate-500">{formatNumber(sale.items_count)} ítems</p>
                                        )}
                                    </td>
                                    <td className="px-2 py-3">
                                        <div className="flex flex-wrap gap-1">
                                            {(sale.payments_summary ?? []).map((payment) => (
                                                <span key={`${sale.id}-${payment.method}`} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                                                    {payment.method_label}: {formatCurrency(payment.amount)}
                                                </span>
                                            ))}
                                        </div>
                                    </td>
                                    <td className="px-2 py-3 text-right font-semibold">{formatCurrency(sale.total)}</td>
                                    <td className="px-2 py-3">
                                        <p className="font-medium">{sale.cashier?.name ?? '—'}</p>
                                        <p className="text-xs text-slate-500">{sale.cashier?.email ?? ''}</p>
                                    </td>
                                    <td className="px-2 py-3 text-right">
                                        <Link
                                            href={`/app/gestion/reportes/ventas/${sale.id}`}
                                            className="text-sm font-medium text-slate-900 underline-offset-4 hover:underline"
                                        >
                                            Ver
                                        </Link>
                                    </td>
                                </tr>
                            ))}
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

function formatDate(value: string) {
    return new Intl.DateTimeFormat('es-AR', {
        dateStyle: 'medium',
        timeStyle: 'short',
    }).format(new Date(value));
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

type StatusBadgeProps = {
    status: 'completed' | 'cancelled';
    label: string;
};

function StatusBadge({ status, label }: StatusBadgeProps) {
    const styles =
        status === 'completed'
            ? 'bg-emerald-50 text-emerald-700 border border-emerald-100'
            : 'bg-rose-50 text-rose-700 border border-rose-100';
    return <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${styles}`}>{label}</span>;
}
