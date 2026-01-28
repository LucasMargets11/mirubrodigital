"use client";

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

import { MenuPicker, type MenuProductSelection } from '@/components/orders/menu-picker';
import { TableMapEmbed } from '@/components/orders/table-map-embed';
import { useCommercialSettingsQuery } from '@/features/gestion/hooks';
import { cancelOrder, createOrderItem, startOrder } from '@/features/orders/api';
import type { Order } from '@/features/orders/types';
import { tablesKeys, useRestaurantTablesMapState } from '@/features/tables/hooks';
import type { RestaurantTableNode } from '@/features/tables/types';
import { ApiError } from '@/lib/api/client';
import { formatCurrency } from '@/lib/format';

type CartItem = {
    id: string;
    name: string;
    price: number;
    quantity: number;
    sku: string | null;
    categoryName: string | null;
};

type OrderSubmissionPayload = {
    tableId: string;
    customerName: string;
    note: string;
    cartItems: CartItem[];
};

type NewOrderClientProps = {
    canViewCommercialSettings?: boolean;
};

export function NewOrderClient({ canViewCommercialSettings = false }: NewOrderClientProps) {
    const searchParams = useSearchParams();
    const pathname = usePathname();
    const router = useRouter();
    const queryClient = useQueryClient();
    const searchInputRef = useRef<HTMLInputElement>(null);

    const defaultTableId = searchParams.get('tableId');
    const [tableId, setTableId] = useState<string | null>(defaultTableId);
    const [customerName, setCustomerName] = useState('');
    const [note, setNote] = useState('');
    const [cartItems, setCartItems] = useState<CartItem[]>([]);
    const [blockedMessage, setBlockedMessage] = useState<string | null>(null);
    const [formError, setFormError] = useState<string | null>(null);

    const mapStateQuery = useRestaurantTablesMapState();
    const settingsQuery = useCommercialSettingsQuery({
        enabled: canViewCommercialSettings,
        skipIfForbidden: !canViewCommercialSettings,
    });

    const tables = mapStateQuery.data?.tables ?? [];
    const tablesLayout = mapStateQuery.data?.layout;
    const allowSellWithoutStock = canViewCommercialSettings
        ? settingsQuery.data?.allow_sell_without_stock ?? false
        : false;

    useEffect(() => {
        if (!tableId || tables.length === 0) {
            return;
        }
        const exists = tables.some((table) => table.id === tableId);
        if (!exists) {
            setTableId(null);
        }
    }, [tables, tableId]);

    const selectedTable = useMemo<RestaurantTableNode | null>(() => tables.find((table) => table.id === tableId) ?? null, [tables, tableId]);
    const cartSubtotal = useMemo(
        () => cartItems.reduce((total, item) => total + item.price * item.quantity, 0),
        [cartItems]
    );

    const handleSelectTable = (nextId: string, snapshot?: RestaurantTableNode | null) => {
        setFormError(null);
        if (snapshot?.state === 'PAUSED') {
            setBlockedMessage('Esta mesa está pausada. Reactivala desde la configuración para tomar pedidos.');
            return;
        }
        if (snapshot?.state === 'DISABLED') {
            setBlockedMessage('Mesa deshabilitada. Editá la configuración para volver a mostrarla.');
            return;
        }
        if (snapshot?.state === 'OCCUPIED' && snapshot.active_order) {
            router.push(`/app/orders/${snapshot.active_order.id}`);
            return;
        }
        setBlockedMessage(null);
        setTableId(nextId);
        const params = new URLSearchParams(searchParams.toString());
        params.set('tableId', nextId);
        const query = params.toString();
        router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    };

    const handleClearTable = () => {
        setTableId(null);
        setFormError(null);
        const params = new URLSearchParams(searchParams.toString());
        params.delete('tableId');
        const query = params.toString();
        router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    };

    const handleAddProduct = (selection: MenuProductSelection) => {
        setBlockedMessage(null);
        setFormError(null);
        setCartItems((prev) => {
            const existing = prev.find((item) => item.id === selection.id);
            if (existing) {
                return prev.map((item) =>
                    item.id === selection.id ? { ...item, quantity: item.quantity + 1 } : item
                );
            }
            return [
                ...prev,
                {
                    id: selection.id,
                    name: selection.name,
                    price: selection.price,
                    quantity: 1,
                    sku: selection.sku ?? null,
                    categoryName: selection.categoryName ?? null,
                },
            ];
        });
    };

    const handleAdjustQuantity = (id: string, delta: number) => {
        setCartItems((prev) =>
            prev
                .map((item) =>
                    item.id === id ? { ...item, quantity: Math.max(0, item.quantity + delta) } : item
                )
                .filter((item) => item.quantity > 0)
        );
    };

    const handleRemoveItem = (id: string) => {
        setCartItems((prev) => prev.filter((item) => item.id !== id));
    };

    const createOrderMutation = useMutation<Order, unknown, OrderSubmissionPayload>({
        mutationFn: async ({ tableId: payloadTableId, customerName: namePayload, note: notePayload, cartItems: items }) => {
            let createdOrderId: string | null = null;
            try {
                const started = await startOrder({
                    table_id: payloadTableId,
                    channel: 'dine_in',
                    customer_name: namePayload.trim() || undefined,
                    note: notePayload.trim() || undefined,
                });
                createdOrderId = started.id;
                let snapshot = started;
                for (const item of items) {
                    snapshot = await createOrderItem(createdOrderId, {
                        name: item.name,
                        quantity: item.quantity,
                        unit_price: item.price,
                    });
                }
                return snapshot;
            } catch (error) {
                if (createdOrderId) {
                    try {
                        await cancelOrder(createdOrderId);
                    } catch {
                        // best-effort rollback
                    }
                }
                throw error;
            }
        },
        onSuccess: async () => {
            setCartItems([]);
            setCustomerName('');
            setNote('');
            setFormError(null);
            await Promise.all([
                queryClient.invalidateQueries({ queryKey: tablesKeys.status() }),
                queryClient.invalidateQueries({ queryKey: ['orders'] }),
            ]);
            router.push('/app/orders');
        },
        onError: (error) => {
            if (error instanceof ApiError) {
                const payload = error.payload as { detail?: string } | undefined;
                setFormError(payload?.detail ?? 'No pudimos crear la orden. Intentá nuevamente.');
                return;
            }
            setFormError('No pudimos crear la orden. Intentá nuevamente.');
        },
    });

    const handleConfirmOrder = () => {
        if (!tableId) {
            setFormError('Seleccioná una mesa antes de confirmar.');
            return;
        }
        if (cartItems.length === 0) {
            setFormError('Agregá al menos un producto antes de confirmar.');
            return;
        }
        setFormError(null);
        createOrderMutation.mutate({ tableId, customerName, note, cartItems });
    };

    const tablesLoading = mapStateQuery.isLoading;
    const tablesError = mapStateQuery.isError ? 'No pudimos cargar las mesas. Intentá nuevamente.' : null;
    const submitDisabled = !tableId || cartItems.length === 0 || createOrderMutation.isPending;

    return (
        <section data-testid="new-order-root" className="space-y-6">
            <header className="space-y-2">
                <p className="text-xs uppercase tracking-wide text-slate-400">Nueva orden</p>
                <h1 className="text-3xl font-semibold text-slate-900">Crear pedido</h1>
                <p className="text-sm text-slate-500">
                    Seleccioná una mesa desde el mapa y agregá productos para abrir una orden inmediata en la vista principal.
                </p>
            </header>
            <div className="grid gap-6 lg:grid-cols-[420px_1fr] xl:grid-cols-[480px_1fr]">
                <TableMapEmbed
                    tables={tables}
                    layout={tablesLayout}
                    selectedTableId={tableId ?? undefined}
                    loading={tablesLoading}
                    error={tablesError}
                    onSelectTable={(id, snapshot) => handleSelectTable(id, snapshot)}
                />
                <div className="space-y-4">
                    {blockedMessage ? (
                        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                            <div className="flex items-start justify-between gap-4">
                                <span>{blockedMessage}</span>
                                <button
                                    type="button"
                                    onClick={() => setBlockedMessage(null)}
                                    className="text-xs font-semibold uppercase text-amber-700"
                                >
                                    Cerrar
                                </button>
                            </div>
                        </div>
                    ) : null}
                    <MenuPicker
                        onProductSelect={handleAddProduct}
                        allowSellWithoutStock={allowSellWithoutStock}
                        onBlockedSelection={setBlockedMessage}
                        searchInputRef={searchInputRef}
                    />
                </div>
            </div>
            <div className="grid gap-6 lg:grid-cols-[420px_1fr] xl:grid-cols-[480px_1fr]">
                <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                    <div className="flex items-center justify-between gap-3">
                        <div>
                            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Mesa asignada</p>
                            {selectedTable ? (
                                <div className="text-sm text-slate-600">
                                    <p className="text-base font-semibold text-slate-900">{selectedTable.name}</p>
                                    <span className="text-xs text-slate-500">
                                        Estado: {selectedTable.active_order?.status_label ?? selectedTable.state}
                                    </span>
                                    {selectedTable.state === 'OCCUPIED' && selectedTable.active_order ? (
                                        <span className="block text-xs font-semibold text-rose-600">
                                            Mesa ocupada por orden #{selectedTable.active_order.number}
                                        </span>
                                    ) : selectedTable.state === 'FREE' ? (
                                        <span className="block text-xs text-emerald-600">Lista para tomar la orden</span>
                                    ) : selectedTable.state === 'PAUSED' ? (
                                        <span className="block text-xs text-amber-600">Mesa pausada. Reactivala desde configuración.</span>
                                    ) : null}
                                </div>
                            ) : (
                                <p className="text-sm text-slate-500">Seleccioná una mesa para sincronizarla con el mapa.</p>
                            )}
                        </div>
                        {selectedTable ? (
                            <button
                                type="button"
                                onClick={handleClearTable}
                                className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900"
                            >
                                Quitar mesa
                            </button>
                        ) : null}
                    </div>
                    <form className="space-y-3">
                        <label className="text-sm font-medium text-slate-700">
                            Cliente
                            <input
                                type="text"
                                value={customerName}
                                onChange={(event) => setCustomerName(event.target.value)}
                                className="mt-1 w-full rounded-2xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                placeholder="Opcional"
                            />
                        </label>
                        <label className="text-sm font-medium text-slate-700">
                            Nota interna
                            <textarea
                                value={note}
                                onChange={(event) => setNote(event.target.value)}
                                className="mt-1 w-full rounded-2xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                rows={3}
                                placeholder="Alergias, sector, etc."
                            />
                        </label>
                    </form>
                </div>
                <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Carrito</p>
                            <h3 className="text-lg font-semibold text-slate-900">Resumen del pedido</h3>
                        </div>
                        <span className="text-xs text-slate-500">{cartItems.length} ítems</span>
                    </div>
                    {cartItems.length === 0 ? (
                        <p className="rounded-2xl border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
                            Comenzá agregando productos desde la carta.
                        </p>
                    ) : (
                        <ul className="space-y-3">
                            {cartItems.map((item) => (
                                <li key={item.id} className="rounded-2xl border border-slate-100 bg-slate-50 p-3">
                                    <div className="flex items-start justify-between gap-4">
                                        <div>
                                            <p className="text-sm font-semibold text-slate-900">{item.name}</p>
                                            <p className="text-xs text-slate-500">
                                                {item.categoryName ?? 'Sin categoría'} {item.sku ? `· SKU ${item.sku}` : ''}
                                            </p>
                                        </div>
                                        <button
                                            type="button"
                                            onClick={() => handleRemoveItem(item.id)}
                                            className="text-xs font-semibold uppercase text-slate-400 hover:text-slate-700"
                                        >
                                            Quitar
                                        </button>
                                    </div>
                                    <div className="mt-3 flex items-center justify-between gap-3">
                                        <div className="flex items-center gap-2 rounded-full bg-white px-2 py-1 text-sm text-slate-700">
                                            <button
                                                type="button"
                                                onClick={() => handleAdjustQuantity(item.id, -1)}
                                                className="rounded-full px-2 text-base leading-none text-slate-500 hover:text-slate-900"
                                            >
                                                –
                                            </button>
                                            <span className="w-6 text-center font-semibold">{item.quantity}</span>
                                            <button
                                                type="button"
                                                onClick={() => handleAdjustQuantity(item.id, 1)}
                                                className="rounded-full px-2 text-base leading-none text-slate-500 hover:text-slate-900"
                                            >
                                                +
                                            </button>
                                        </div>
                                        <p className="text-sm font-semibold text-slate-900">
                                            {formatCurrency(item.price * item.quantity)}
                                        </p>
                                    </div>
                                </li>
                            ))}
                        </ul>
                    )}
                    <div className="space-y-3 border-t border-slate-100 pt-4">
                        <div className="flex items-center justify-between text-sm text-slate-600">
                            <span>Subtotal</span>
                            <strong className="text-base text-slate-900">{formatCurrency(cartSubtotal)}</strong>
                        </div>
                        {formError ? (
                            <p className="rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">
                                {formError}
                            </p>
                        ) : null}
                        <button
                            type="button"
                            onClick={handleConfirmOrder}
                            className="w-full rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                            disabled={submitDisabled}
                        >
                            {createOrderMutation.isPending ? 'Creando orden...' : 'Confirmar orden'}
                        </button>
                        <p className="text-xs text-slate-400">
                            Cada confirmación abre la orden y bloquea la mesa hasta que la cobres o canceles desde la vista principal.
                        </p>
                    </div>
                </div>
            </div>
        </section>
    );
}
