'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import { downloadCsv } from '@/lib/csv';
import { formatCurrency, formatNumber } from '@/lib/format';
import { useReportsPayments } from '@/features/reports/hooks';

import { ReportsFilters, type ReportsFiltersValue } from '@/modules/reports/components/filters';
import { ReportsPagination } from '@/modules/reports/components/pagination';

const defaultRange = getDefaultRange();

export function ReportsPaymentsClient() {
    const [filters, setFilters] = useState<ReportsFiltersValue>({
        preset: 'last7',
        from: defaultRange.from,
        to: defaultRange.to,
    });
    const [limit] = useState(25);
    const [offset, setOffset] = useState(0);

    useEffect(() => {
        setOffset(0);
    }, [filters]);

    const queryFilters = useMemo(
        () => ({
            from: filters.from,
            to: filters.to,
            payment_method: filters.paymentMethod,
            method: filters.method,
            register_id: filters.registerId,
            user_id: filters.userId,
            limit,
            offset,
        }),
        [filters, limit, offset],
    );

    const { data, isLoading, isError } = useReportsPayments(queryFilters);

    const handleExport = () => {
        if (!data) {
            return;
        }
        downloadCsv(`reportes-pagos-${filters.from}-${filters.to}`, [
            {
                title: 'Pagos por método',
                headers: ['Método', 'Total', 'Pagos', 'Ventas'],
                rows: (data.breakdown ?? []).map((row) => [
                    row.method_label,
                    row.amount_total,
                    row.payments_count,
                    row.sales_count,
                ]),
            },
            {
                title: 'Pagos',
                headers: ['Fecha', 'Venta', 'Monto', 'Método', 'Caja', 'Cajero'],
                rows: (data.results ?? []).map((payment) => [
                    formatDate(payment.created_at),
                    `#${payment.sale_number}`,
                    payment.amount,
                    payment.method_label,
                    payment.register?.name ?? '—',
                    payment.cashier?.name ?? '—',
                ]),
            },
        ]);
    };

    return (
        <div className="space-y-6">
            <ReportsFilters
                value={filters}
                onChange={setFilters}
                showPaymentMethod
                showMethod
                showRegister
                showUser
            />

            <section className="rounded-3xl border border-slate-200 bg-white/80 p-4 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Pagos</p>
                        <h2 className="text-2xl font-semibold text-slate-900">Ingresos por método</h2>
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
                    <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                        Error al cargar pagos.
                    </div>
                )}

                <div className="mt-6 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {(data?.breakdown ?? []).map((row) => (
                        <div key={row.method} className="rounded-3xl border border-slate-200 bg-gradient-to-br from-white to-slate-50 p-4">
                            <p className="text-sm font-medium text-slate-500">{row.method_label}</p>
                            <p className="mt-2 text-2xl font-semibold text-slate-900">{formatCurrency(row.amount_total)}</p>
                            <p className="text-xs text-slate-500">
                                {formatNumber(row.payments_count)} pagos • {formatNumber(row.sales_count)} ventas
                            </p>
                        </div>
                    ))}
                    {!data?.breakdown?.length && !isLoading && (
                        <div className="rounded-3xl border border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
                            Sin información para el rango indicado.
                        </div>
                    )}
                </div>

                <div className="mt-8 overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-left text-slate-500">
                                <th className="px-2 py-2 font-medium">Fecha</th>
                                <th className="px-2 py-2 font-medium">Venta</th>
                                <th className="px-2 py-2 font-medium">Método</th>
                                <th className="px-2 py-2 font-medium">Caja</th>
                                <th className="px-2 py-2 font-medium">Cajero</th>
                                <th className="px-2 py-2 font-medium text-right">Monto</th>
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading && (
                                <tr>
                                    <td colSpan={6} className="px-2 py-6 text-center text-slate-500">
                                        Cargando pagos...
                                    </td>
                                </tr>
                            )}
                            {!isLoading && !data?.results?.length && (
                                <tr>
                                    <td colSpan={6} className="px-2 py-6 text-center text-slate-500">
                                        No se registraron pagos.
                                    </td>
                                </tr>
                            )}
                            {(data?.results ?? []).map((payment) => (
                                <tr key={payment.id} className="border-t border-slate-100 text-slate-700">
                                    <td className="px-2 py-3">{formatDate(payment.created_at)}</td>
                                    <td className="px-2 py-3">
                                        <Link
                                            href={`/app/gestion/reportes/ventas/${payment.sale_id}`}
                                            className="font-semibold text-slate-900 underline-offset-4 hover:underline"
                                        >
                                            #{payment.sale_number}
                                        </Link>
                                        <p className="text-xs text-slate-500">Total venta: {formatCurrency(payment.sale_total)}</p>
                                    </td>
                                    <td className="px-2 py-3">
                                        <p className="font-medium">{payment.method_label}</p>
                                        {payment.reference && <p className="text-xs text-slate-500">Ref: {payment.reference}</p>}
                                    </td>
                                    <td className="px-2 py-3">{payment.register?.name ?? '—'}</td>
                                    <td className="px-2 py-3">
                                        <p className="font-medium">{payment.cashier?.name ?? '—'}</p>
                                        <p className="text-xs text-slate-500">{payment.cashier?.email ?? ''}</p>
                                    </td>
                                    <td className="px-2 py-3 text-right font-semibold">{formatCurrency(payment.amount)}</td>
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

function getDefaultRange() {
    const to = new Date();
    const from = new Date();
    from.setDate(to.getDate() - 6);
    return { from: toIso(from), to: toIso(to) };
}

function toIso(date: Date) {
    return date.toISOString().slice(0, 10);
}

function formatDate(value: string) {
    return new Intl.DateTimeFormat('es-AR', {
        dateStyle: 'medium',
        timeStyle: 'short',
    }).format(new Date(value));
}
