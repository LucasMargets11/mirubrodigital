"use client";

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';

import { useOrders } from '@/features/gestion/hooks';
import type { OrdersFilters } from '@/features/gestion/types';

function formatCurrency(value: string | number) {
    const numeric = typeof value === 'number' ? value : Number(value);
    return new Intl.NumberFormat('es-AR', {
        style: 'currency',
        currency: 'ARS',
        minimumFractionDigits: 0,
        maximumFractionDigits: 2,
    }).format(Number.isNaN(numeric) ? 0 : numeric);
}

const statusStyles: Record<string, string> = {
    draft: 'bg-slate-100 text-slate-700',
    pending_confirmation: 'bg-amber-100 text-amber-700',
    confirmed: 'bg-blue-100 text-blue-700',
    in_preparation: 'bg-indigo-100 text-indigo-700',
    ready_for_delivery: 'bg-purple-100 text-purple-700',
    delivered: 'bg-emerald-100 text-emerald-700',
    cancelled: 'bg-rose-100 text-rose-700',
};

const paymentStatusStyles: Record<string, string> = {
    pending: 'text-rose-600',
    partial: 'text-amber-600',
    paid: 'text-emerald-600',
};

type OrdersClientProps = {
    canCreate: boolean;
    canViewQuotes?: boolean;
};

export function OrdersClient({ canCreate, canViewQuotes = false }: OrdersClientProps) {
    const pathname = usePathname();
    
    const [filters, setFilters] = useState<OrdersFilters>({
        search: '',
        status: '',
        date_from: '',
        date_to: '',
    });

    const ordersQuery = useOrders(filters);
    const orders = ordersQuery.data?.results ?? [];
    const totalCount = ordersQuery.data?.count ?? 0;

    const handleFilterChange = (key: keyof OrdersFilters, value: string) => {
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
                        <h2 className="text-2xl font-semibold text-slate-900">Pedidos</h2>
                        <p className="text-sm text-slate-500">Gestión de encargos y entregas.</p>
                    </div>
                    <div className="flex items-center gap-2">
                        {canCreate ? (
                            <Link
                                href="/app/gestion/ventas/pedidos/nuevo"
                                className="inline-flex items-center justify-center rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white hover:bg-slate-800"
                            >
                                Nuevo pedido
                            </Link>
                        ) : null}
                    </div>
                </div>
                 <div className="flex gap-2 border-t border-slate-200 pt-3">
                        <Link
                            href="/app/gestion/ventas"
                            className="rounded-full px-4 py-1.5 text-sm font-medium transition-colors text-slate-600 hover:bg-slate-100"
                        >
                            Ventas
                        </Link>
                        {canViewQuotes ? (
                            <Link
                                href="/app/gestion/ventas/presupuestos"
                                className="rounded-full px-4 py-1.5 text-sm font-medium transition-colors text-slate-600 hover:bg-slate-100"
                            >
                                Presupuestos
                            </Link>
                        ) : null}
                        <Link
                            href="/app/gestion/ventas/pedidos"
                            className="rounded-full px-4 py-1.5 text-sm font-medium transition-colors bg-slate-900 text-white"
                        >
                            Pedidos
                        </Link>
                    </div>
            </header>

            <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
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
                        <option value="draft">Borrador</option>
                        <option value="pending_confirmation">Pendiente Conf.</option>
                        <option value="confirmed">Confirmado</option>
                        <option value="in_preparation">En preparación</option>
                        <option value="ready_for_delivery">Listo entrega</option>
                        <option value="delivered">Entregado</option>
                        <option value="cancelled">Cancelado</option>
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

                <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-100 text-sm">
                        <thead>
                            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                                <th className="px-3 py-2">Pedido</th>
                                <th className="px-3 py-2">Fecha</th>
                                <th className="px-3 py-2">Cliente</th>
                                <th className="px-3 py-2">Estado</th>
                                <th className="px-3 py-2">Pago</th>
                                <th className="px-3 py-2 text-right">Total</th>
                                <th className="px-3 py-2" />
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                             {ordersQuery.isLoading && (
                                <tr>
                                    <td colSpan={7} className="px-3 py-6 text-center text-slate-500">
                                        Cargando pedidos...
                                    </td>
                                </tr>
                            )}
                            {!ordersQuery.isLoading && orders.length === 0 && (
                                <tr>
                                    <td colSpan={7} className="px-3 py-6 text-center text-slate-500">
                                        No hay pedidos registrados.
                                    </td>
                                </tr>
                            )}
                            {orders.map((order: any) => (
                                <tr key={order.id} className="hover:bg-slate-50">
                                    <td className="px-3 py-3">
                                        <Link href={`/app/gestion/ventas/pedidos/${order.id}`} className="font-semibold text-slate-900 hover:underline">
                                           {order.number}
                                        </Link>
                                    </td>
                                    <td className="px-3 py-3 text-slate-500">
                                        {new Date(order.created_at).toLocaleDateString()}
                                    </td>
                                    <td className="px-3 py-3">{order.customer_name}</td>
                                    <td className="px-3 py-3">
                                        <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${statusStyles[order.status] ?? 'bg-slate-100 text-slate-600'}`}>
                                            {order.status_display}
                                        </span>
                                    </td>
                                    <td className="px-3 py-3">
                                         <span className={`font-medium ${paymentStatusStyles[order.payment_status]}`}>
                                            {order.payment_status_display}
                                         </span>
                                         {order.payment_status !== 'paid' && (
                                            <div className="text-xs text-slate-400">
                                                Restan: {formatCurrency(order.pending_balance)}
                                            </div>
                                         )}
                                    </td>
                                    <td className="px-3 py-3 text-right font-medium">
                                        {formatCurrency(order.total)}
                                    </td>
                                    <td className="px-3 py-3 text-right">
                                        <Link 
                                            href={`/app/gestion/ventas/pedidos/${order.id}`}
                                            className="text-slate-400 hover:text-slate-600"
                                        >
                                            Ver detalle
                                        </Link>
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
