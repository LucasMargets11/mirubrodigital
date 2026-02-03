"use client";

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';

import { MenuPicker, type MenuProductSelection } from '@/components/orders/menu-picker';
import { OrderSummaryClient } from '@/components/orders/order-summary-client';
import { TableMapEmbed } from '@/components/orders/table-map-embed';
import { useCommercialSettingsQuery } from '@/features/gestion/hooks';
import {
    useAddOrderItem,
    useOrder,
    useRemoveOrderItem,
    useUpdateOrder,
    useUpdateOrderItem,
} from '@/features/orders/hooks';
import type { Order, OrderItem } from '@/features/orders/types';
import { useRestaurantTablesMapState } from '@/features/tables/hooks';
import type { RestaurantTableNode } from '@/features/tables/types';
import { ApiError } from '@/lib/api/client';
import { formatCurrency } from '@/lib/format';
import { cn } from '@/lib/utils';

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

const DEFAULT_PAYMENT_REDIRECT = '/app/cash';

type OrderEditClientProps = {
    orderId: string;
    initialOrder?: Order;
    canUpdate: boolean;
    canClose: boolean;
    canAssignTable: boolean;
    canViewCommercialSettings?: boolean;
    invoicesFeatureEnabled: boolean;
    canIssueInvoices: boolean;
    canViewInvoices: boolean;
};

export function OrderEditClient({
    orderId,
    initialOrder,
    canUpdate,
    canClose,
    canAssignTable,
    canViewCommercialSettings = false,
    invoicesFeatureEnabled,
    canIssueInvoices,
    canViewInvoices,
}: OrderEditClientProps) {
    const router = useRouter();
    const [formState, setFormState] = useState({ customerName: '', note: '' });
    const [blockedMessage, setBlockedMessage] = useState<string | null>(null);
    const [actionError, setActionError] = useState<string | null>(null);

    const orderQuery = useOrder(orderId, { refetchInterval: 10000, initialData: initialOrder });
    const order = orderQuery.data ?? initialOrder ?? null;
    const canMutateOrder = Boolean(order?.is_editable) && canUpdate;
    const canAssignTables = Boolean(order?.is_editable) && canAssignTable;
    const canCloseOrder = Boolean(order?.is_editable) && canClose;

    const updateOrderMutation = useUpdateOrder(orderId);
    const addItemMutation = useAddOrderItem(orderId);
    const updateItemMutation = useUpdateOrderItem(orderId);
    const removeItemMutation = useRemoveOrderItem(orderId);

    const tablesMapQuery = useRestaurantTablesMapState({ enabled: canAssignTable, refetchInterval: 5000 });

    const settingsQuery = useCommercialSettingsQuery({
        enabled: canViewCommercialSettings,
        skipIfForbidden: !canViewCommercialSettings,
    });

    const allowSellWithoutStock = canViewCommercialSettings
        ? settingsQuery.data?.allow_sell_without_stock ?? false
        : false;

    useEffect(() => {
        if (!order) {
            return;
        }
        setFormState({ customerName: order.customer_name ?? '', note: order.note ?? '' });
    }, [order?.id, order?.customer_name, order?.note]);

    const tables = tablesMapQuery.data?.tables ?? [];
    const tablesLayout = tablesMapQuery.data?.layout;

    const selectedTable: RestaurantTableNode | null = useMemo(() => {
        if (!order?.table_id) {
            return null;
        }
        return tables.find((table) => table.id === order.table_id) ?? null;
    }, [order?.table_id, tables]);

    const subtotalDisplay = order ? formatCurrency(order.subtotal_amount ?? order.total_amount) : formatCurrency(0);
    const totalDisplay = order ? formatCurrency(order.total_amount) : formatCurrency(0);

    const tablesError = tablesMapQuery.isError ? 'No pudimos cargar las mesas.' : null;

    const handleDetailChange = (field: 'customerName' | 'note', value: string) => {
        setFormState((prev) => ({ ...prev, [field]: value }));
    };

    const handleSaveDetails = () => {
        if (!order || !canMutateOrder) {
            return;
        }
        setActionError(null);
        updateOrderMutation.mutate(
            {
                customer_name: formState.customerName,
                note: formState.note,
            },
            {
                onError: (error) => setActionError(resolveErrorMessage(error)),
            }
        );
    };

    const handleSelectTable = (tableId: string, snapshot?: RestaurantTableNode | null) => {
        if (!order || !canAssignTables) {
            return;
        }
        if (order.table_id === tableId) {
            return;
        }
        if (snapshot?.state === 'PAUSED') {
            setBlockedMessage('La mesa está pausada. Reactivala desde configuración antes de asignarla.');
            return;
        }
        if (snapshot?.state === 'DISABLED') {
            setBlockedMessage('La mesa está deshabilitada en la configuración.');
            return;
        }
        if (snapshot?.state === 'OCCUPIED' && snapshot.active_order && snapshot.active_order.id !== order.id) {
            setBlockedMessage(`Mesa ocupada por la orden #${snapshot.active_order.number}.`);
            return;
        }
        setActionError(null);
        updateOrderMutation.mutate(
            {
                table_id: tableId,
            },
            {
                onError: (error) => setActionError(resolveErrorMessage(error)),
            }
        );
    };

    const handleClearTable = () => {
        if (!order || !canAssignTables) {
            return;
        }
        if (!order.table_id) {
            return;
        }
        setActionError(null);
        updateOrderMutation.mutate(
            {
                table_id: null,
            },
            {
                onError: (error) => setActionError(resolveErrorMessage(error)),
            }
        );
    };

    const handleAddProduct = (selection: MenuProductSelection) => {
        if (!canMutateOrder) {
            return;
        }
        setBlockedMessage(null);
        setActionError(null);
        addItemMutation.mutate(
            {
                name: selection.name,
                quantity: 1,
                unit_price: selection.price,
            },
            {
                onError: (error) => setActionError(resolveErrorMessage(error)),
            }
        );
    };

    const handleAdjustQuantity = (item: OrderItem, delta: number) => {
        if (!canMutateOrder) {
            return;
        }
        const currentQuantity = Number(item.quantity);
        const nextQuantity = Number((currentQuantity + delta).toFixed(2));
        if (nextQuantity <= 0) {
            removeItemMutation.mutate(item.id, {
                onError: (error) => setActionError(resolveErrorMessage(error)),
            });
            return;
        }
        updateItemMutation.mutate(
            {
                itemId: item.id,
                payload: { quantity: nextQuantity },
            },
            {
                onError: (error) => setActionError(resolveErrorMessage(error)),
            }
        );
    };

    const handleRemoveItem = (item: OrderItem) => {
        if (!canMutateOrder) {
            return;
        }
        removeItemMutation.mutate(item.id, {
            onError: (error) => setActionError(resolveErrorMessage(error)),
        });
    };

    const handleRedirectToCash = () => {
        if (!order || !canCloseOrder) {
            return;
        }
        router.push(`${DEFAULT_PAYMENT_REDIRECT}?orderId=${order.id}`);
    };

    const isMutatingItems = addItemMutation.isPending || updateItemMutation.isPending || removeItemMutation.isPending;

    if (!order && orderQuery.isLoading) {
        return (
            <section className="space-y-4">
                <div className="h-10 w-48 animate-pulse rounded-full bg-slate-200" />
                <div className="grid gap-4 lg:grid-cols-2">
                    {Array.from({ length: 4 }).map((_, index) => (
                        <div key={`skeleton-${index}`} className="h-48 animate-pulse rounded-3xl bg-slate-100" />
                    ))}
                </div>
            </section>
        );
    }

    if (!order) {
        return (
            <section className="space-y-4">
                <header className="space-y-2">
                    <p className="text-xs uppercase tracking-wide text-slate-400">Orden</p>
                    <h1 className="text-3xl font-semibold text-slate-900">No encontramos la orden</h1>
                    <p className="text-sm text-slate-500">Verificá el enlace o volvé a la lista de órdenes.</p>
                </header>
                <Link
                    href="/app/orders"
                    className="inline-flex items-center gap-2 rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:border-slate-900 hover:text-slate-900"
                >
                    Volver al tablero
                </Link>
            </section>
        );
    }

    if (!order.is_editable) {
        return (
            <OrderSummaryClient
                orderId={order.id}
                initialOrder={order}
                invoicesFeatureEnabled={invoicesFeatureEnabled}
                canIssueInvoices={canIssueInvoices}
                canViewInvoices={canViewInvoices}
            />
        );
    }

    const statusMeta = STATUS_META[order.status];
    const channelMeta = CHANNEL_META[order.channel];

    return (
        <section className="space-y-6" data-testid="order-edit-root">
            <header className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="space-y-2">
                    <p className="text-xs uppercase tracking-wide text-slate-400">Orden #{order.number}</p>
                    <h1 className="text-3xl font-semibold text-slate-900">Editar pedido</h1>
                    <div className="flex flex-wrap items-center gap-2 text-xs font-semibold">
                        <span className={cn('rounded-full px-3 py-1', statusMeta.badge)}>{order.status_label}</span>
                        <span className={cn('rounded-full px-3 py-1', channelMeta.badge)}>{order.channel_label}</span>
                        {order.table_name ? (
                            <span className="rounded-full bg-white/60 px-3 py-1 text-slate-600">Mesa {order.table_name}</span>
                        ) : (
                            <span className="rounded-full bg-white/60 px-3 py-1 text-slate-500">Sin mesa</span>
                        )}
                    </div>
                    <p className="text-sm text-slate-500">Última actualización {formatTimestamp(order.updated_at)}</p>
                </div>
                <div className="flex flex-wrap gap-3">
                    <Link
                        href="/app/orders"
                        className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:border-slate-900 hover:text-slate-900"
                    >
                        Volver a órdenes
                    </Link>
                    {canCloseOrder ? (
                        <button
                            type="button"
                            onClick={handleRedirectToCash}
                            className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800"
                        >
                            Cobrar en caja
                        </button>
                    ) : null}
                </div>
            </header>
            {actionError ? (
                <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-700">{actionError}</p>
            ) : null}
            <div className="grid gap-6 xl:grid-cols-[380px_1fr]">
                <div className="space-y-4">
                    <div className="space-y-4 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Mesa asignada</p>
                                {selectedTable ? (
                                    <div className="space-y-1 text-sm text-slate-600">
                                        <p className="text-base font-semibold text-slate-900">{selectedTable.name}</p>
                                        <p className="text-xs text-slate-500">Código {selectedTable.code}</p>
                                        <p className="text-xs text-slate-500">
                                            Estado: {selectedTable.active_order?.status_label ?? selectedTable.state}
                                        </p>
                                    </div>
                                ) : (
                                    <p className="text-sm text-slate-500">Sin mesa asignada.</p>
                                )}
                            </div>
                            {canAssignTables ? (
                                <button
                                    type="button"
                                    onClick={handleClearTable}
                                    disabled={!order.table_id || updateOrderMutation.isPending || !canAssignTables}
                                    className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900 disabled:opacity-50"
                                >
                                    Liberar mesa
                                </button>
                            ) : null}
                        </div>
                        <div className="space-y-3">
                            <label className="text-sm font-semibold text-slate-700">
                                Cliente
                                <input
                                    type="text"
                                    value={formState.customerName}
                                    onChange={(event) => handleDetailChange('customerName', event.target.value)}
                                    disabled={!canMutateOrder}
                                    className="mt-1 w-full rounded-2xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-100"
                                />
                            </label>
                            <label className="text-sm font-semibold text-slate-700">
                                Nota interna
                                <textarea
                                    value={formState.note}
                                    onChange={(event) => handleDetailChange('note', event.target.value)}
                                    disabled={!canMutateOrder}
                                    rows={3}
                                    className="mt-1 w-full rounded-2xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-100"
                                />
                            </label>
                            {canMutateOrder ? (
                                <button
                                    type="button"
                                    onClick={handleSaveDetails}
                                    disabled={updateOrderMutation.isPending}
                                    className="w-full rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-60"
                                >
                                    Guardar cambios
                                </button>
                            ) : null}
                        </div>
                    </div>
                    {canAssignTables ? (
                        <TableMapEmbed
                            tables={tables}
                            layout={tablesLayout}
                            selectedTableId={order.table_id}
                            loading={tablesMapQuery.isLoading}
                            error={tablesError}
                            onSelectTable={(id, snapshot) => handleSelectTable(id, snapshot)}
                        />
                    ) : (
                        <div className="rounded-3xl border border-dashed border-slate-200 bg-white px-4 py-5 text-sm text-slate-500">
                            La orden está cerrada y no permite reasignar mesas.
                        </div>
                    )}
                </div>
                <div className="space-y-4">
                    <div className="space-y-4 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Ítems</p>
                                <h2 className="text-xl font-semibold text-slate-900">{order.items.length} productos</h2>
                            </div>
                            <div className="text-right">
                                <p className="text-xs uppercase tracking-wide text-slate-400">Total</p>
                                <p className="text-2xl font-semibold text-slate-900">{totalDisplay}</p>
                                <p className="text-xs text-slate-500">Subtotal {subtotalDisplay}</p>
                            </div>
                        </div>
                        {order.items.length === 0 ? (
                            <p className="rounded-2xl border border-dashed border-slate-200 px-4 py-10 text-center text-sm text-slate-500">
                                Agregá productos desde la carta para comenzar.
                            </p>
                        ) : (
                            <ul className="space-y-3">
                                {order.items.map((item) => (
                                    <li key={item.id} className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                                        <div className="flex flex-wrap items-start justify-between gap-3">
                                            <div>
                                                <p className="text-sm font-semibold text-slate-900">
                                                    {Number(item.quantity).toLocaleString('es-AR', { maximumFractionDigits: 2 })} × {item.name}
                                                </p>
                                                {item.note ? <p className="text-xs text-slate-500">{item.note}</p> : null}
                                                {item.sold_without_stock ? (
                                                    <span className="mt-1 inline-flex items-center rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-semibold text-rose-700">
                                                        Sin stock
                                                    </span>
                                                ) : null}
                                            </div>
                                            <div className="text-right">
                                                <p className="text-sm font-semibold text-slate-900">{formatCurrency(item.total_price)}</p>
                                                <p className="text-xs text-slate-500">{formatCurrency(item.unit_price)} c/u</p>
                                            </div>
                                        </div>
                                        {canMutateOrder ? (
                                            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                                                <div className="flex items-center gap-2 rounded-full bg-white px-2 py-1 text-sm font-semibold text-slate-700">
                                                    <button
                                                        type="button"
                                                        onClick={() => handleAdjustQuantity(item, -1)}
                                                        disabled={isMutatingItems}
                                                        className="rounded-full px-2 text-base leading-none text-slate-500 hover:text-slate-900 disabled:opacity-50"
                                                    >
                                                        –
                                                    </button>
                                                    <span className="w-6 text-center">{Number(item.quantity).toLocaleString('es-AR', { maximumFractionDigits: 1 })}</span>
                                                    <button
                                                        type="button"
                                                        onClick={() => handleAdjustQuantity(item, 1)}
                                                        disabled={isMutatingItems}
                                                        className="rounded-full px-2 text-base leading-none text-slate-500 hover:text-slate-900 disabled:opacity-50"
                                                    >
                                                        +
                                                    </button>
                                                </div>
                                                <button
                                                    type="button"
                                                    onClick={() => handleRemoveItem(item)}
                                                    disabled={isMutatingItems}
                                                    className="text-xs font-semibold uppercase text-slate-400 hover:text-rose-600 disabled:opacity-50"
                                                >
                                                    Quitar
                                                </button>
                                            </div>
                                        ) : null}
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                    <div className="space-y-4">
                        {blockedMessage ? (
                            <p className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">{blockedMessage}</p>
                        ) : null}
                        {canMutateOrder ? (
                            <MenuPicker
                                onProductSelect={handleAddProduct}
                                allowSellWithoutStock={allowSellWithoutStock}
                                onBlockedSelection={setBlockedMessage}
                            />
                        ) : (
                            <div className="rounded-3xl border border-dashed border-slate-200 bg-white px-4 py-6 text-sm text-slate-500">
                                La orden está cerrada y no se pueden agregar productos.
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </section>
    );
}

function resolveErrorMessage(error: unknown): string {
    if (error instanceof ApiError) {
        const payload = error.payload as { detail?: string; error?: { message?: string } } | undefined;
        return payload?.error?.message ?? payload?.detail ?? 'Ocurrió un error inesperado.';
    }
    if (typeof error === 'object' && error && 'message' in error) {
        return String((error as { message?: string }).message ?? 'Ocurrió un error inesperado.');
    }
    return 'Ocurrió un error inesperado.';
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
