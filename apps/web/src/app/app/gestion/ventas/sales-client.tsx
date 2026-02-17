"use client";

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';

import { useSales } from '@/features/gestion/hooks';
import type { SalesFilters } from '@/features/gestion/types';

function formatCurrency(value: string | number) {
    const numeric = typeof value === 'number' ? value : Number(value);
    return new Intl.NumberFormat('es-AR', {
        style: 'currency',
        currency: 'ARS',
        maximumFractionDigits: 2,
    }).format(Number.isNaN(numeric) ? 0 : numeric);
}

const statusStyles: Record<string, string> = {
    completed: 'bg-emerald-100 text-emerald-700',
    cancelled: 'bg-rose-100 text-rose-700',
};

type SalesClientProps = {
    canCreate: boolean;
    canViewQuotes?: boolean;
    canCreateQuotes?: boolean;
};

export function SalesClient({ canCreate, canViewQuotes = false, canCreateQuotes = false }: SalesClientProps) {
    const pathname = usePathname();
    const isQuotesRoute = pathname?.includes('/presupuestos');
    
    const [filters, setFilters] = useState<SalesFilters>({
        search: '',
        status: '',
        payment_method: '',
        date_from: '',
        date_to: '',
    });

    const salesQuery = useSales(filters, { enabled: !isQuotesRoute });
    const sales = salesQuery.data?.results ?? [];
    const totalCount = salesQuery.data?.count ?? 0;

    const handleFilterChange = (key: keyof SalesFilters, value: string) => {
        setFilters((prev) => ({
            ...prev,
            [key]: value,
        }));
    };

    return (
        <section className="space-y-4">
            <header className="flex flex-col gap-3 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                        <h2 className="text-2xl font-semibold text-slate-900">Ventas</h2>
                        <p className="text-sm text-slate-500">Lista de operaciones registradas en el negocio.</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        {canCreate ? (
                            <Link
                                href="/app/gestion/ventas/nueva"
                                className="inline-flex items-center justify-center rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white hover:bg-slate-800"
                            >
                                Nueva venta
                            </Link>
                        ) : null}
                        {canCreateQuotes ? (
                            <Link
                                href="/app/gestion/ventas/presupuestos/nuevo"
                                className="inline-flex items-center justify-center rounded-full border border-slate-300 bg-white px-5 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                            >
                                Crear presupuesto
                            </Link>
                        ) : null}
                    </div>
                </div>
                {canViewQuotes ? (
                    <div className="flex gap-2 border-t border-slate-200 pt-3">
                        <Link
                            href="/app/gestion/ventas"
                            className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                                !isQuotesRoute
                                    ? 'bg-slate-900 text-white'
                                    : 'text-slate-600 hover:bg-slate-100'
                            }`}
                        >
                            Ventas
                        </Link>
                        <Link
                            href="/app/gestion/ventas/presupuestos"
                            className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                                isQuotesRoute
                                    ? 'bg-slate-900 text-white'
                                    : 'text-slate-600 hover:bg-slate-100'
                            }`}
                        >
                            Presupuestos
                        </Link>
                    </div>
                ) : null}
            </header>

            {!isQuotesRoute && (
                <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                    {salesQuery.isError ? (
                        <p className="mb-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
                            No pudimos cargar las ventas. Intentá de nuevo en unos segundos.
                        </p>
                    ) : null}
                <div className="grid gap-3 md:grid-cols-5">
                    <input
                        type="search"
                        value={filters.search ?? ''}
                        onChange={(event) => handleFilterChange('search', event.target.value)}
                        placeholder="Buscar cliente o #"
                        className="rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none md:col-span-2"
                    />
                    <select
                        value={filters.status ?? ''}
                        onChange={(event) => handleFilterChange('status', event.target.value)}
                        className="rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
                    >
                        <option value="">Todos los estados</option>
                        <option value="completed">Completadas</option>
                        <option value="cancelled">Canceladas</option>
                    </select>
                    <select
                        value={filters.payment_method ?? ''}
                        onChange={(event) => handleFilterChange('payment_method', event.target.value)}
                        className="rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
                    >
                        <option value="">Todos los medios</option>
                        <option value="cash">Efectivo</option>
                        <option value="card">Tarjeta</option>
                        <option value="transfer">Transferencia</option>
                        <option value="other">Otro</option>
                    </select>
                    <input
                        type="date"
                        value={filters.date_from ?? ''}
                        onChange={(event) => handleFilterChange('date_from', event.target.value)}
                        className="rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
                    />
                    <input
                        type="date"
                        value={filters.date_to ?? ''}
                        onChange={(event) => handleFilterChange('date_to', event.target.value)}
                        className="rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
                    />
                </div>
                <p className="mt-3 text-xs uppercase tracking-wide text-slate-400">{totalCount} registros</p>
                <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-100 text-sm">
                        <thead>
                            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                                <th className="px-3 py-2">Venta</th>
                                <th className="px-3 py-2">Fecha</th>
                                <th className="px-3 py-2">Cliente</th>
                                <th className="px-3 py-2">Medio</th>
                                <th className="px-3 py-2">Items</th>
                                <th className="px-3 py-2 text-right">Total</th>
                                <th className="px-3 py-2" />
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {salesQuery.isLoading && (
                                <tr>
                                    <td colSpan={7} className="px-3 py-6 text-center text-slate-500">
                                        Cargando ventas...
                                    </td>
                                </tr>
                            )}
                            {!salesQuery.isLoading && sales.length === 0 && (
                                <tr>
                                    <td colSpan={7} className="px-3 py-6 text-center text-slate-500">
                                        Aún no registraste ventas.
                                    </td>
                                </tr>
                            )}
                            {sales.map((sale) => (
                                <tr key={sale.id} className="hover:bg-slate-50">
                                    <td className="px-3 py-3">
                                        <div className="flex items-center gap-2">
                                            <span className="font-semibold text-slate-900">#{sale.number}</span>
                                            <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${statusStyles[sale.status] ?? 'bg-slate-100 text-slate-600'}`}>
                                                {sale.status_label}
                                            </span>
                                        </div>
                                    </td>
                                    <td className="px-3 py-3 text-slate-500">
                                        {new Date(sale.created_at).toLocaleString('es-AR', {
                                            dateStyle: 'medium',
                                            timeStyle: 'short',
                                        })}
                                    </td>
                                    <td className="px-3 py-3">
                                        <p className="font-medium text-slate-900">{sale.customer?.name || sale.customer_name || 'Sin cliente'}</p>
                                        {sale.customer && (sale.customer.doc_number || sale.customer.email || sale.customer.phone) ? (
                                            <p className="text-xs text-slate-400">
                                                {sale.customer.doc_number
                                                    ? `${sale.customer.doc_type?.toUpperCase() ?? ''} ${sale.customer.doc_number}`.trim()
                                                    : sale.customer.email || sale.customer.phone}
                                            </p>
                                        ) : null}
                                        {sale.notes ? <p className="text-xs text-slate-400 line-clamp-1">{sale.notes}</p> : null}
                                    </td>
                                    <td className="px-3 py-3 text-slate-500">{sale.payment_method_label}</td>
                                    <td className="px-3 py-3 text-slate-500">{sale.items_count ?? '—'}</td>
                                    <td className="px-3 py-3 text-right font-semibold text-slate-900">{formatCurrency(sale.total)}</td>
                                    <td className="px-3 py-3 text-right">
                                        <Link
                                            href={`/app/gestion/ventas/${sale.id}`}
                                            className="text-sm font-semibold text-slate-600 hover:text-slate-900"
                                        >
                                            Ver detalle →
                                        </Link>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
            )}
        </section>
    );
}
