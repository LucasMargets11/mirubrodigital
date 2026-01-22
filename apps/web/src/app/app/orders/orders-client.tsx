"use client";

import { useMemo, useState } from 'react';

import { Modal } from '@/components/ui/modal';
import { useCreateOrder, useOrders, useUpdateOrderStatus } from '@/features/orders/hooks';
import type { OrderChannel, OrderStatus } from '@/features/orders/types';

const STATUS_FILTERS: { id: string; label: string; statuses: OrderStatus[] }[] = [
    { id: 'active', label: 'En curso', statuses: ['pending', 'preparing'] },
    { id: 'ready', label: 'Listas', statuses: ['ready'] },
    { id: 'delivered', label: 'Entregadas', statuses: ['delivered'] },
    { id: 'canceled', label: 'Canceladas', statuses: ['canceled'] },
];

const STATUS_META: Record<OrderStatus, { label: string; badge: string }> = {
    pending: { label: 'Pendiente', badge: 'bg-amber-100 text-amber-700' },
    preparing: { label: 'En preparación', badge: 'bg-sky-100 text-sky-700' },
    ready: { label: 'Lista para entregar', badge: 'bg-emerald-100 text-emerald-700' },
    delivered: { label: 'Entregada', badge: 'bg-slate-200 text-slate-700' },
    canceled: { label: 'Cancelada', badge: 'bg-rose-100 text-rose-700' },
};

const NEXT_STATUS: Partial<Record<OrderStatus, OrderStatus>> = {
    pending: 'preparing',
    preparing: 'ready',
    ready: 'delivered',
};

const CHANNEL_BADGES: Record<OrderChannel, string> = {
    dine_in: 'bg-indigo-50 text-indigo-700',
    pickup: 'bg-teal-50 text-teal-700',
    delivery: 'bg-amber-50 text-amber-700',
};

type ItemFormState = {
    name: string;
    quantity: string;
    unit_price: string;
    note: string;
};

type OrderFormState = {
    table_name: string;
    customer_name: string;
    channel: OrderChannel;
    note: string;
    items: ItemFormState[];
};

const createEmptyItem = (): ItemFormState => ({ name: '', quantity: '1', unit_price: '', note: '' });

const emptyForm: OrderFormState = {
    table_name: '',
    customer_name: '',
    channel: 'dine_in',
    note: '',
    items: [createEmptyItem()],
};

type OrdersClientProps = {
    canCreate: boolean;
    canUpdate: boolean;
};

function formatCurrency(value: string | number) {
    const numeric = typeof value === 'string' ? Number(value) : value;
    if (Number.isNaN(numeric)) {
        return '$0';
    }
    return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 2 }).format(numeric);
}

function formatTimestamp(iso: string) {
    const date = new Date(iso);
    return date.toLocaleString('es-AR', { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' });
}

export function OrdersClient({ canCreate, canUpdate }: OrdersClientProps) {
    const [selectedFilter, setSelectedFilter] = useState<string>(STATUS_FILTERS[0].id);
    const [modalOpen, setModalOpen] = useState(false);
    const [form, setForm] = useState<OrderFormState>(emptyForm);
    const [formError, setFormError] = useState<string | null>(null);
    const [boardError, setBoardError] = useState<string | null>(null);

    const filterConfig = STATUS_FILTERS.find((filter) => filter.id === selectedFilter) ?? STATUS_FILTERS[0];
    const ordersQuery = useOrders(filterConfig.statuses);
    const createMutation = useCreateOrder();
    const updateStatusMutation = useUpdateOrderStatus();

    const orders = useMemo(() => ordersQuery.data ?? [], [ordersQuery.data]);

    "use client";

    import { useMemo, useState } from 'react';

    import { Modal } from '@/components/ui/modal';
    import { useCreateOrder, useOrders, useUpdateOrderStatus } from '@/features/orders/hooks';
    import type { OrderChannel, OrderStatus } from '@/features/orders/types';

    const STATUS_FILTERS: { id: string; label: string; statuses: OrderStatus[] }[] = [
        { id: 'active', label: 'En curso', statuses: ['pending', 'preparing'] },
        { id: 'ready', label: 'Listas', statuses: ['ready'] },
        { id: 'delivered', label: 'Entregadas', statuses: ['delivered'] },
        { id: 'canceled', label: 'Canceladas', statuses: ['canceled'] },
    ];

    const STATUS_META: Record<OrderStatus, { label: string; badge: string }> = {
        pending: { label: 'Pendiente', badge: 'bg-amber-100 text-amber-700' },
        preparing: { label: 'En preparación', badge: 'bg-sky-100 text-sky-700' },
        ready: { label: 'Lista para entregar', badge: 'bg-emerald-100 text-emerald-700' },
        delivered: { label: 'Entregada', badge: 'bg-slate-200 text-slate-700' },
        canceled: { label: 'Cancelada', badge: 'bg-rose-100 text-rose-700' },
    };

    const NEXT_STATUS: Partial<Record<OrderStatus, OrderStatus>> = {
        pending: 'preparing',
        preparing: 'ready',
        ready: 'delivered',
    };

    const CHANNEL_BADGES: Record<OrderChannel, string> = {
        dine_in: 'bg-indigo-50 text-indigo-700',
        pickup: 'bg-teal-50 text-teal-700',
        delivery: 'bg-amber-50 text-amber-700',
    };

    type ItemFormState = {
        name: string;
        quantity: string;
        unit_price: string;
        note: string;
    };

    type OrderFormState = {
        table_name: string;
        customer_name: string;
        channel: OrderChannel;
        note: string;
        items: ItemFormState[];
    };

    const createEmptyItem = (): ItemFormState => ({ name: '', quantity: '1', unit_price: '', note: '' });

    const emptyForm: OrderFormState = {
        table_name: '',
        customer_name: '',
        channel: 'dine_in',
        note: '',
        items: [createEmptyItem()],
    };

    type OrdersClientProps = {
        canCreate: boolean;
        canUpdate: boolean;
    };

    function formatCurrency(value: string | number) {
        const numeric = typeof value === 'string' ? Number(value) : value;
        if (Number.isNaN(numeric)) {
            return '$0';
        }
        return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 2 }).format(numeric);
    }

    function formatTimestamp(iso: string) {
        const date = new Date(iso);
        return date.toLocaleString('es-AR', { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' });
    }

    export function OrdersClient({ canCreate, canUpdate }: OrdersClientProps) {
        const [selectedFilter, setSelectedFilter] = useState<string>(STATUS_FILTERS[0].id);
        const [modalOpen, setModalOpen] = useState(false);
        const [form, setForm] = useState<OrderFormState>(emptyForm);
        const [formError, setFormError] = useState<string | null>(null);
        const [boardError, setBoardError] = useState<string | null>(null);

        const filterConfig = STATUS_FILTERS.find((filter) => filter.id === selectedFilter) ?? STATUS_FILTERS[0];
        const ordersQuery = useOrders(filterConfig.statuses);
        const createMutation = useCreateOrder();
        const updateStatusMutation = useUpdateOrderStatus();

        const orders = useMemo(() => ordersQuery.data ?? [], [ordersQuery.data]);

        const handleOpenModal = () => {
            setForm(emptyForm);
            setFormError(null);
            setModalOpen(true);
        };

        const handleCloseModal = () => {
            setModalOpen(false);
        };

        const handleItemChange = (index: number, field: keyof ItemFormState, value: string) => {
            setForm((prev) => {
                const nextItems = [...prev.items];
                nextItems[index] = { ...nextItems[index], [field]: value };
                return { ...prev, items: nextItems };
            });
        };

        const handleAddItem = () => {
            setForm((prev) => ({ ...prev, items: [...prev.items, createEmptyItem()] }));
        };

        const handleRemoveItem = (index: number) => {
            setForm((prev) => {
                if (prev.items.length === 1) {
                    return prev;
                }
                const nextItems = prev.items.filter((_, i) => i !== index);
                return { ...prev, items: nextItems.length ? nextItems : [createEmptyItem()] };
            });
        };

        const handleCreateOrder = async () => {
            const normalizedItems = form.items
                .map((item) => ({
                    name: item.name.trim(),
                    quantity: Number(item.quantity),
                    unit_price: Number(item.unit_price),
                    note: item.note.trim(),
                }))
                .filter((item) => item.name && item.quantity > 0);

            if (!normalizedItems.length) {
                setFormError('Agregá al menos un item válido.');
                return;
            }

            setFormError(null);
            try {
                await createMutation.mutateAsync({
                    channel: form.channel,
                    table_name: form.table_name.trim() || undefined,
                    customer_name: form.customer_name.trim() || undefined,
                    note: form.note.trim() || undefined,
                    items: normalizedItems,
                });
                setModalOpen(false);
                setForm(emptyForm);
            } catch (error) {
                setFormError('No pudimos crear la orden. Reintentá en unos segundos.');
            }
        };

        const handleStatusUpdate = async (orderId: string, status: OrderStatus) => {
            setBoardError(null);
            try {
                await updateStatusMutation.mutateAsync({ orderId, status });
            } catch (error) {
                setBoardError('No pudimos actualizar el estado.');
            }
        };

        const isSubmitting = createMutation.isPending;
        const isUpdatingStatus = updateStatusMutation.isPending;

        const formTotal = form.items.reduce((acc, item) => {
            const quantity = Number(item.quantity);
            const price = Number(item.unit_price);
            if (Number.isNaN(quantity) || Number.isNaN(price)) {
                return acc;
            }
            return acc + quantity * price;
        }, 0);

        return (
            <section className="space-y-6">
                <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                    <div>
                        <p className="text-xs uppercase tracking-wide text-slate-400">Servicio Restaurante</p>
                        <h1 className="text-3xl font-semibold text-slate-900">Órdenes en sala</h1>
                        <p className="text-sm text-slate-500">Seguimiento en tiempo real del salón, take-away y delivery.</p>
                    </div>
                    {canCreate ? (
                        <button
                            type="button"
                            onClick={handleOpenModal}
                            className="self-start rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800"
                        >
                            Nueva orden
                        </button>
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
                <div className="space-y-3 text-sm text-slate-500">
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
                        const statusInfo = STATUS_META[order.status];
                        const nextStatus = NEXT_STATUS[order.status];
                        const channelBadge = CHANNEL_BADGES[order.channel] ?? 'bg-slate-100 text-slate-700';
                        const isTerminal = order.status === 'delivered' || order.status === 'canceled';
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
                                    {order.note && <p className="rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-500">Nota: {order.note}</p>}
                                </div>
                                <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
                                    <div className="text-slate-500">Actualizado {formatTimestamp(order.updated_at)}</div>
                                    <div className="text-right text-xl font-semibold text-slate-900">
                                        {formatCurrency(order.total_amount)}
                                    </div>
                                </div>
                                {canUpdate && !isTerminal ? (
                                    <div className="flex flex-wrap gap-2">
                                        {nextStatus ? (
                                            <button
                                                type="button"
                                                disabled={isUpdatingStatus}
                                                onClick={() => handleStatusUpdate(order.id, nextStatus)}
                                                className="rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60"
                                            >
                                                Marcar {STATUS_META[nextStatus].label.toLowerCase()}
                                            </button>
                                        ) : null}
                                        <button
                                            type="button"
                                            disabled={isUpdatingStatus}
                                            onClick={() => handleStatusUpdate(order.id, 'canceled')}
                                            className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-600 transition hover:border-rose-400 hover:text-rose-600 disabled:opacity-60"
                                        >
                                            Cancelar
                                        </button>
                                    </div>
                                ) : null}
                            </article>
                        );
                    })}
                </div>
                <Modal open={modalOpen} onClose={handleCloseModal} title="Nueva orden">
                    <div className="grid gap-4 md:grid-cols-2">
                        <label className="text-sm font-medium text-slate-700">
                            Mesa / Sector
                            <input
                                type="text"
                                value={form.table_name}
                                onChange={(event) => setForm((prev) => ({ ...prev, table_name: event.target.value }))}
                                className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            />
                        </label>
                        <label className="text-sm font-medium text-slate-700">
                            Cliente
                            <input
                                type="text"
                                value={form.customer_name}
                                onChange={(event) => setForm((prev) => ({ ...prev, customer_name: event.target.value }))}
                                className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            />
                        </label>
                    </div>
                    <label className="text-sm font-medium text-slate-700">
                        Canal
                        <select
                            value={form.channel}
                            onChange={(event) => setForm((prev) => ({ ...prev, channel: event.target.value as OrderChannel }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        >
                            <option value="dine_in">Salón</option>
                            <option value="pickup">Retiro</option>
                            <option value="delivery">Delivery</option>
                        </select>
                    </label>
                    <label className="text-sm font-medium text-slate-700">
                        Nota interna
                        <textarea
                            value={form.note}
                            onChange={(event) => setForm((prev) => ({ ...prev, note: event.target.value }))}
                            rows={3}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        />
                    </label>
                    <div className="space-y-4">
                        <p className="text-sm font-semibold text-slate-700">Items</p>
                        {form.items.map((item, index) => (
                            <div key={`item-${index}`} className="rounded-2xl border border-slate-200 p-4">
                                <div className="grid gap-3 md:grid-cols-2">
                                    <label className="text-xs font-medium uppercase tracking-wide text-slate-500">
                                        Nombre
                                        <input
                                            type="text"
                                            value={item.name}
                                            onChange={(event) => handleItemChange(index, 'name', event.target.value)}
                                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                        />
                                    </label>
                                    <label className="text-xs font-medium uppercase tracking-wide text-slate-500">
                                        Nota
                                        <input
                                            type="text"
                                            value={item.note}
                                            onChange={(event) => handleItemChange(index, 'note', event.target.value)}
                                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                        />
                                    </label>
                                </div>
                                <div className="mt-3 grid gap-3 md:grid-cols-3">
                                    <label className="text-xs font-medium uppercase tracking-wide text-slate-500">
                                        Cantidad
                                        <input
                                            type="number"
                                            min="0"
                                            step="0.1"
                                            value={item.quantity}
                                            onChange={(event) => handleItemChange(index, 'quantity', event.target.value)}
                                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                        />
                                    </label>
                                    <label className="text-xs font-medium uppercase tracking-wide text-slate-500">
                                        Precio unitario
                                        <input
                                            type="number"
                                            min="0"
                                            step="0.1"
                                            value={item.unit_price}
                                            onChange={(event) => handleItemChange(index, 'unit_price', event.target.value)}
                                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                        />
                                    </label>
                                    <div className="flex items-end justify-between">
                                        <p className="text-xs text-slate-500">Subtotal</p>
                                        <p className="text-sm font-semibold text-slate-900">
                                            {formatCurrency(Number(item.quantity) * Number(item.unit_price))}
                                        </p>
                                    </div>
                                </div>
                                {form.items.length > 1 ? (
                                    <button
                                        type="button"
                                        onClick={() => handleRemoveItem(index)}
                                        className="mt-3 text-xs font-semibold text-rose-600"
                                    >
                                        Quitar item
                                    </button>
                                ) : null}
                            </div>
                        ))}
                        <button
                            type="button"
                            onClick={handleAddItem}
                            className="text-sm font-semibold text-slate-900"
                        >
                            + Agregar item
                        </button>
                    </div>
                    <div className="flex items-center justify-between rounded-2xl bg-slate-50 px-4 py-3 text-sm">
                        <span>Total estimado</span>
                        <span className="text-lg font-semibold text-slate-900">{formatCurrency(formTotal)}</span>
                    </div>
                    {formError ? <p className="text-sm text-rose-600">{formError}</p> : null}
                    <div className="flex justify-end gap-3 pt-2">
                        <button
                            type="button"
                            onClick={handleCloseModal}
                            className="rounded-full border border-slate-300 px-5 py-2 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900"
                        >
                            Cancelar
                        </button>
                        <button
                            type="button"
                            onClick={handleCreateOrder}
                            disabled={isSubmitting}
                            className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-60"
                        >
                            {isSubmitting ? 'Creando...' : 'Crear orden'}
                        </button>
                    </div>
                </Modal>
            </section>
        );
    }
