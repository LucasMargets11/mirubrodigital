"use client";

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import { ToastBubble, type ToastTone } from '@/components/app/toast';
import { OrderCheckoutDrawer } from '@/components/orders/order-checkout-drawer';
import { useOrders, useUpdateOrderStatus } from '@/features/orders/hooks';
import type { Order, OrderChannel, OrderStatus } from '@/features/orders/types';

const STATUS_FILTERS: { id: string; label: string; statuses: OrderStatus[] }[] = [
    { id: 'active', label: 'En curso', statuses: ['open', 'sent'] },
    { id: 'paid', label: 'Pagadas', statuses: ['paid'] },
    { id: 'cancelled', label: 'Canceladas', statuses: ['cancelled'] },
    { id: 'drafts', label: 'Borradores', statuses: ['draft'] },
];

const STATUS_META: Record<OrderStatus, { label: string; badge: string }> = {
    draft: { label: 'Borrador', badge: 'bg-slate-300 text-slate-700' },
    open: { label: 'Abierta', badge: 'bg-amber-100 text-amber-700' },
    sent: { label: 'Enviada a cocina', badge: 'bg-sky-100 text-sky-700' },
    paid: { label: 'Pagada', badge: 'bg-emerald-100 text-emerald-700' },
    cancelled: { label: 'Cancelada', badge: 'bg-rose-100 text-rose-700' },
};

const NEXT_STATUS: Partial<Record<OrderStatus, OrderStatus>> = {
    draft: 'open',
    open: 'sent',
};

const CHANNEL_BADGES: Record<OrderChannel, string> = {
    dine_in: 'bg-indigo-50 text-indigo-700',
    pickup: 'bg-teal-50 text-teal-700',
    delivery: 'bg-amber-50 text-amber-700',
};

type OrdersClientProps = {
    canCreate: boolean;
    canUpdate: boolean;
    canClose: boolean;
};

function formatCurrency(value: string | number) {
    const numeric = typeof value === 'string' ? Number(value) : value;
    if (Number.isNaN(numeric)) {
        return '$0';
    }
    return new Intl.NumberFormat('es-AR', {
        style: 'currency',
        currency: 'ARS',
        maximumFractionDigits: 2,
    }).format(numeric);
}

function formatTimestamp(iso: string) {
    const date = new Date(iso);
    return date.toLocaleString('es-AR', { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' });
}

export function OrdersClient({ canCreate, canUpdate, canClose }: OrdersClientProps) {
    const [selectedFilter, setSelectedFilter] = useState<string>(STATUS_FILTERS[0].id);
    const [boardError, setBoardError] = useState<string | null>(null);
    const [checkoutOrder, setCheckoutOrder] = useState<Order | null>(null);
    const [checkoutToast, setCheckoutToast] = useState<{ message: string; tone: ToastTone } | null>(null);

    const filterConfig = STATUS_FILTERS.find((filter) => filter.id === selectedFilter) ?? STATUS_FILTERS[0];
    const ordersQuery = useOrders(filterConfig.statuses);
    const updateStatusMutation = useUpdateOrderStatus();

    const orders = useMemo(() => ordersQuery.data ?? [], [ordersQuery.data]);

    const handleStatusUpdate = async (orderId: string, status: OrderStatus) => {
        setBoardError(null);
        try {
            await updateStatusMutation.mutateAsync({ orderId, status });
        } catch (error) {
            setBoardError('No pudimos actualizar el estado.');
        }
    };

    const handleOpenCheckout = (target: Order) => {
        setCheckoutOrder(target);
    };

    useEffect(() => {
        if (!checkoutToast) {
            return;
        }
        const timer = setTimeout(() => setCheckoutToast(null), 4000);
        return () => clearTimeout(timer);
    }, [checkoutToast]);

    const isUpdatingStatus = updateStatusMutation.isPending;

    return (
        <section className="space-y-6">
            <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div>
                    <p className="text-xs uppercase tracking-wide text-slate-400">Servicio Restaurante</p>
                    <h1 className="text-3xl font-semibold text-slate-900">Órdenes en sala</h1>
                    <p className="text-sm text-slate-500">Seguimiento en tiempo real del salón, take-away y delivery.</p>
                </div>
                {canCreate ? (
                    <Link
                        href="/app/orders/new"
                        className="self-start rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800"
                    >
                        Nueva orden
                    </Link>
                ) : null}
            </header>
            <div className="flex flex-wrap gap-2">
                {STATUS_FILTERS.map((filter) => (
                    <button
                        key={filter.id}
                        type="button"
                        onClick={() => setSelectedFilter(filter.id)}
                        className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${selectedFilter === filter.id
                            ? 'border-slate-900 bg-slate-900 text-white'
                            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-900 hover:text-slate-900'
                            }`}
                    >
                        {filter.label}
                    </button>
                ))}
            </div>
            <div className="space-y-2 text-sm text-slate-500">
                {ordersQuery.isLoading && <p>Cargando órdenes...</p>}
                {ordersQuery.isError && <p className="text-rose-600">No pudimos cargar las órdenes.</p>}
                {boardError && <p className="text-rose-600">{boardError}</p>}
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
                {!ordersQuery.isLoading && orders.length === 0 ? (
                    <div className="col-span-full rounded-2xl border border-dashed border-slate-200 bg-white px-6 py-12 text-center">
                        <p className="text-base font-semibold text-slate-900">Sin órdenes en esta vista</p>
                        <p className="mt-2 text-sm text-slate-500">Cambiar el filtro o crear una nueva orden para comenzar.</p>
                    </div>
                ) : null}
                {orders.map((order) => {
                    const statusInfo = STATUS_META[order.status] ?? {
                        label: order.status_label,
                        badge: 'bg-slate-200 text-slate-700',
                    };
                    const nextStatus = NEXT_STATUS[order.status];
                    const channelBadge = CHANNEL_BADGES[order.channel] ?? 'bg-slate-100 text-slate-700';
                    const isTerminal = ['paid', 'cancelled'].includes(order.status);
                    const canCharge = canClose && ['open', 'sent'].includes(order.status);
                    return (
                        <article key={order.id} className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                            <div className="flex flex-wrap items-center gap-2">
                                <span className="text-sm font-semibold text-slate-400">#{order.number}</span>
                                <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${statusInfo.badge}`}>{statusInfo.label}</span>
                                <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${channelBadge}`}>{order.channel_label}</span>
                                {order.table_name ? <span className="text-xs text-slate-500">Mesa {order.table_name}</span> : null}
                            </div>
                            <div className="space-y-2 text-sm text-slate-700">
                                {order.customer_name && <p className="font-medium text-slate-900">Cliente: {order.customer_name}</p>}
                                <ul className="space-y-1">
                                    {order.items.map((item) => (
                                        <li key={item.id} className="flex items-center justify-between">
                                            <span>
                                                {Number(item.quantity).toLocaleString('es-AR', { maximumFractionDigits: 2 })} × {item.name}
                                                {item.note ? <span className="text-xs text-slate-400"> · {item.note}</span> : null}
                                            </span>
                                            <span className="font-semibold text-slate-900">{formatCurrency(item.total_price)}</span>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                            <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
                                <div className="text-slate-500">Actualizado {formatTimestamp(order.updated_at)}</div>
                                <div className="text-right text-xl font-semibold text-slate-900">{formatCurrency(order.total_amount)}</div>
                            </div>
                            {(canUpdate || canCharge) && !isTerminal ? (
                                <div className="flex flex-wrap gap-2">
                                    <Link
                                        href={`/app/orders/${order.id}`}
                                        className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-900 hover:text-slate-900"
                                    >
                                        Abrir orden
                                    </Link>
                                    {canCharge ? (
                                        <button
                                            type="button"
                                            onClick={() => handleOpenCheckout(order)}
                                            className="rounded-full border border-lime-300 px-4 py-2 text-sm font-semibold text-lime-700 transition hover:border-lime-500 hover:text-lime-900"
                                        >
                                            Cobrar orden
                                        </button>
                                    ) : null}
                                    {canUpdate && nextStatus ? (
                                        <button
                                            type="button"
                                            disabled={isUpdatingStatus}
                                            onClick={() => handleStatusUpdate(order.id, nextStatus)}
                                            className="rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60"
                                        >
                                            Marcar {STATUS_META[nextStatus].label.toLowerCase()}
                                        </button>
                                    ) : null}
                                    {canUpdate ? (
                                        <button
                                            type="button"
                                            disabled={isUpdatingStatus}
                                            onClick={() => handleStatusUpdate(order.id, 'cancelled')}
                                            className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-600 transition hover:border-rose-400 hover:text-rose-600 disabled:opacity-60"
                                        >
                                            Cancelar
                                        </button>
                                    ) : null}
                                </div>
                            ) : (
                                <Link
                                    href={`/app/orders/${order.id}`}
                                    className="inline-flex rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-900 hover:text-slate-900"
                                >
                                    Ver orden
                                </Link>
                            )}
                        </article>
                    );
                })}
            </div>
            <OrderCheckoutDrawer
                order={checkoutOrder}
                open={Boolean(checkoutOrder)}
                onClose={() => setCheckoutOrder(null)}
                onPaid={(updated) => {
                    setCheckoutToast({ message: 'Orden cobrada, mesa liberada', tone: 'success' });
                    setCheckoutOrder(null);
                }}
            />
            {checkoutToast && <ToastBubble message={checkoutToast.message} tone={checkoutToast.tone} />}
        </section>
    );
}
