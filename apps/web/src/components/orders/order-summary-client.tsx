"use client";

import Link from 'next/link';
import { useMemo } from 'react';

import { InvoiceActions } from '@/components/invoicing/invoice-actions';
import { useOrder } from '@/features/orders/hooks';
import type { Order } from '@/features/orders/types';
import { formatCurrency } from '@/lib/format';

const STATUS_META: Record<Order['status'], { label: string; badge: string }> = {
    draft: { label: 'Borrador', badge: 'bg-slate-200 text-slate-700' },
    open: { label: 'Abierta', badge: 'bg-amber-100 text-amber-700' },
    sent: { label: 'Enviada a cocina', badge: 'bg-sky-100 text-sky-700' },
    paid: { label: 'Pagada', badge: 'bg-emerald-100 text-emerald-700' },
    cancelled: { label: 'Cancelada', badge: 'bg-rose-100 text-rose-700' },
};

const CHANNEL_META: Record<Order['channel'], { badge: string }> = {
    dine_in: { badge: 'bg-indigo-50 text-indigo-700' },
    pickup: { badge: 'bg-teal-50 text-teal-700' },
    delivery: { badge: 'bg-amber-50 text-amber-700' },
};

type OrderSummaryClientProps = {
    orderId: string;
    initialOrder?: Order;
    invoicesFeatureEnabled: boolean;
    canIssueInvoices: boolean;
    canViewInvoices: boolean;
};

export function OrderSummaryClient({
    orderId,
    initialOrder,
    invoicesFeatureEnabled,
    canIssueInvoices,
    canViewInvoices,
}: OrderSummaryClientProps) {
    const orderQuery = useOrder(orderId, { initialData: initialOrder, refetchInterval: 12000 });
    const order = orderQuery.data ?? initialOrder;

    if (!order) {
        return (
            <section className="space-y-4">
                <div className="h-10 w-48 animate-pulse rounded-full bg-slate-200" />
                <div className="grid gap-4 md:grid-cols-2">
                    {Array.from({ length: 4 }).map((_, index) => (
                        <div key={`summary-skeleton-${index}`} className="h-44 animate-pulse rounded-3xl bg-slate-100" />
                    ))}
                </div>
            </section>
        );
    }

    const statusMeta = STATUS_META[order.status];
    const channelMeta = CHANNEL_META[order.channel];
    const itemCount = order.items.length;

    const items = useMemo(() => order.items ?? [], [order.items]);

    return (
        <section className="space-y-6" data-testid="order-summary-root">
            <header className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="space-y-2">
                    <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Orden #{order.number}</p>
                    <h1 className="text-3xl font-semibold text-slate-900">Resumen de orden</h1>
                    <p className="text-sm text-slate-500">
                        Última actualización {formatTimestamp(order.updated_at)} ·{` `}
                        {order.is_paid ? 'Pagada' : statusMeta.label}
                    </p>
                    <div className="flex flex-wrap items-center gap-2 text-xs font-semibold">
                        <span className={`rounded-full px-3 py-1 ${statusMeta.badge}`}>{statusMeta.label}</span>
                        <span className={`rounded-full px-3 py-1 ${channelMeta.badge}`}>{order.channel_label}</span>
                        {order.table_name ? (
                            <span className="rounded-full bg-white/60 px-3 py-1 text-slate-600">Mesa {order.table_name}</span>
                        ) : (
                            <span className="rounded-full bg-white/60 px-3 py-1 text-slate-500">Sin mesa</span>
                        )}
                    </div>
                </div>
                <div className="flex flex-wrap gap-3">
                    <Link
                        href="/app/orders"
                        className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:border-slate-900 hover:text-slate-900"
                    >
                        Volver a órdenes
                    </Link>
                    <button
                        type="button"
                        onClick={() => orderQuery.refetch()}
                        className="rounded-full border border-slate-900 px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-slate-900 hover:text-white"
                    >
                        Actualizar ahora
                    </button>
                </div>
            </header>
            <InvoiceActions
                entityType="order"
                entityId={order.id}
                entityNumber={order.number}
                customerName={order.customer_name}
                existingInvoice={order.invoice}
                featureEnabled={invoicesFeatureEnabled}
                canIssue={canIssueInvoices}
                canViewInvoices={canViewInvoices}
                disabledReason={canIssueInvoices ? undefined : 'No tenés permiso para emitir facturas.'}
            />
            <div className="grid gap-4 lg:grid-cols-2">
                <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                    <h2 className="text-lg font-semibold text-slate-900">Detalle</h2>
                    <dl className="mt-4 space-y-3 text-sm text-slate-600">
                        <div>
                            <dt className="text-xs uppercase tracking-wide text-slate-400">Cliente</dt>
                            <dd className="text-base font-semibold text-slate-900">{order.customer_name || 'Sin cliente'}</dd>
                        </div>
                        <div>
                            <dt className="text-xs uppercase tracking-wide text-slate-400">Canal</dt>
                            <dd className="text-base font-semibold text-slate-900">{order.channel_label}</dd>
                        </div>
                        <div>
                            <dt className="text-xs uppercase tracking-wide text-slate-400">Número de venta</dt>
                            <dd className="text-base font-semibold text-slate-900">
                                {order.sale_number ? `Venta #${order.sale_number}` : 'Sin venta asociada'}
                            </dd>
                        </div>
                    </dl>
                    {order.note ? (
                        <p className="mt-4 rounded-2xl bg-slate-50 p-4 text-sm text-slate-600">{order.note}</p>
                    ) : null}
                </div>
                <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                    <h2 className="text-lg font-semibold text-slate-900">Totales</h2>
                    <div className="mt-4 space-y-2 text-sm text-slate-600">
                        <p className="flex items-center justify-between">
                            <span>Subtotal</span>
                            <span className="font-semibold text-slate-900">{formatCurrency(order.subtotal_amount ?? order.total_amount)}</span>
                        </p>
                        <p className="flex items-center justify-between">
                            <span>Venta asociada</span>
                            <span className="font-semibold text-slate-900">
                                {order.sale_total ? formatCurrency(order.sale_total) : '—'}
                            </span>
                        </p>
                        <p className="flex items-center justify-between text-base font-semibold text-slate-900">
                            <span>Total</span>
                            <span>{formatCurrency(order.total_amount)}</span>
                        </p>
                    </div>
                </div>
            </div>
            <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-xs uppercase tracking-wide text-slate-400">Productos</p>
                        <h2 className="text-xl font-semibold text-slate-900">{itemCount} ítems</h2>
                    </div>
                    <div className="text-right">
                        <p className="text-xs uppercase tracking-wide text-slate-400">Total pagado</p>
                        <p className="text-2xl font-semibold text-slate-900">{formatCurrency(order.total_amount)}</p>
                    </div>
                </div>
                {items.length === 0 ? (
                    <p className="mt-6 rounded-2xl border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
                        La orden no tiene productos asociados.
                    </p>
                ) : (
                    <ul className="mt-6 divide-y divide-slate-100">
                        {items.map((item) => (
                            <li key={item.id} className="py-4">
                                <div className="flex flex-wrap items-center justify-between gap-3">
                                    <div>
                                        <p className="text-sm font-semibold text-slate-900">{item.name}</p>
                                        <p className="text-xs text-slate-500">
                                            {Number(item.quantity).toLocaleString('es-AR', { maximumFractionDigits: 2 })} × {formatCurrency(item.unit_price)}
                                        </p>
                                        {item.note ? <p className="text-xs text-slate-400">Nota: {item.note}</p> : null}
                                    </div>
                                    <p className="text-sm font-semibold text-slate-900">{formatCurrency(item.total_price)}</p>
                                </div>
                            </li>
                        ))}
                    </ul>
                )}
            </section>
        </section>
    );
}

function formatTimestamp(iso: string) {
    const date = new Date(iso);
    return date.toLocaleString('es-AR', {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
    });
}
