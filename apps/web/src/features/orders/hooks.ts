import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { cashKeys } from '@/features/cash/hooks';
import { tablesKeys } from '@/features/tables/hooks';
import {
    closeOrder,
    createSaleFromOrder,
    createOrder,
    createOrderItem,
    deleteOrderItem,
    fetchOrderCheckout,
    fetchOrder,
    fetchOrders,
    payOrder,
    updateOrder,
    updateOrderItem,
    updateOrderStatus,
} from './api';
import type {
    CloseOrderPayload,
    CreateSalePayload,
    Order,
    OrderCheckoutResponse,
    OrderItemCreatePayload,
    OrderItemUpdatePayload,
    OrderPayload,
    OrderStatus,
    OrderUpdatePayload,
    PayOrderPayload,
} from './types';

const ordersBaseKey = ['orders'] as const;
const orderDetailKey = (orderId: string) => [...ordersBaseKey, 'detail', orderId] as const;
const orderCheckoutKey = (orderId: string) => [...ordersBaseKey, 'detail', orderId, 'checkout'] as const;

type UseOrderOptions = {
    enabled?: boolean;
    refetchInterval?: number;
};

export function useOrders(statusFilter: OrderStatus[]) {
    return useQuery({
        queryKey: [...ordersBaseKey, { statusFilter }],
        queryFn: () => fetchOrders({ status: statusFilter, limit: 100 }),
        refetchInterval: 15000,
    });
}

export function useOrder(orderId: string | null, options?: UseOrderOptions) {
    const enabled = Boolean(orderId) && (options?.enabled ?? true);
    const key = orderId ? orderDetailKey(orderId) : [...ordersBaseKey, 'detail', null];
    return useQuery({
        queryKey: key,
        queryFn: () => fetchOrder(orderId as string),
        enabled,
        refetchInterval: enabled && options?.refetchInterval ? options.refetchInterval : false,
    });
}

export function useCreateOrder() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: OrderPayload) => createOrder(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ordersBaseKey });
        },
    });
}

export function useUpdateOrderStatus() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ orderId, status }: { orderId: string; status: OrderStatus }) => updateOrderStatus(orderId, status),
        onSuccess: (order) => {
            queryClient.setQueryData(orderDetailKey(order.id), order);
            queryClient.invalidateQueries({ queryKey: ordersBaseKey });
        },
    });
}

export function useCloseOrder() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ orderId, payload }: { orderId: string; payload: CloseOrderPayload }) =>
            closeOrder(orderId, payload),
        onSuccess: (order) => {
            queryClient.setQueryData(orderDetailKey(order.id), order);
            queryClient.invalidateQueries({ queryKey: ordersBaseKey });
        },
    });
}

export function useUpdateOrder(orderId: string) {
    const queryClient = useQueryClient();
    const detailKey = orderDetailKey(orderId);
    return useMutation({
        mutationFn: (payload: OrderUpdatePayload) => updateOrder(orderId, payload),
        onMutate: async (payload) => {
            await queryClient.cancelQueries({ queryKey: detailKey });
            const previous = queryClient.getQueryData<Order>(detailKey);
            if (previous) {
                const optimistic = applyOrderUpdateOptimistic(previous, payload);
                queryClient.setQueryData(detailKey, optimistic);
            }
            return { previous } as { previous?: Order };
        },
        onError: (_error, _payload, context) => {
            if (context?.previous) {
                queryClient.setQueryData(detailKey, context.previous);
            }
        },
        onSuccess: (order) => {
            queryClient.setQueryData(detailKey, order);
            queryClient.invalidateQueries({ queryKey: ordersBaseKey });
        },
    });
}

export function useAddOrderItem(orderId: string) {
    const queryClient = useQueryClient();
    const detailKey = orderDetailKey(orderId);
    return useMutation({
        mutationFn: (payload: OrderItemCreatePayload) => createOrderItem(orderId, payload),
        onMutate: async (payload) => {
            await queryClient.cancelQueries({ queryKey: detailKey });
            const previous = queryClient.getQueryData<Order>(detailKey);
            if (previous) {
                const optimistic = applyAddItemOptimistic(previous, payload);
                queryClient.setQueryData(detailKey, optimistic);
            }
            return { previous } as { previous?: Order };
        },
        onError: (_error, _payload, context) => {
            if (context?.previous) {
                queryClient.setQueryData(detailKey, context.previous);
            }
        },
        onSuccess: (order) => {
            queryClient.setQueryData(detailKey, order);
            queryClient.invalidateQueries({ queryKey: ordersBaseKey });
        },
    });
}

export function useUpdateOrderItem(orderId: string) {
    const queryClient = useQueryClient();
    const detailKey = orderDetailKey(orderId);
    return useMutation({
        mutationFn: ({ itemId, payload }: { itemId: string; payload: OrderItemUpdatePayload }) =>
            updateOrderItem(orderId, itemId, payload),
        onMutate: async ({ itemId, payload }) => {
            await queryClient.cancelQueries({ queryKey: detailKey });
            const previous = queryClient.getQueryData<Order>(detailKey);
            if (previous) {
                const optimistic = applyUpdateItemOptimistic(previous, itemId, payload);
                queryClient.setQueryData(detailKey, optimistic);
            }
            return { previous } as { previous?: Order };
        },
        onError: (_error, _payload, context) => {
            if (context?.previous) {
                queryClient.setQueryData(detailKey, context.previous);
            }
        },
        onSuccess: (order) => {
            queryClient.setQueryData(detailKey, order);
            queryClient.invalidateQueries({ queryKey: ordersBaseKey });
        },
    });
}

export function useRemoveOrderItem(orderId: string) {
    const queryClient = useQueryClient();
    const detailKey = orderDetailKey(orderId);
    return useMutation({
        mutationFn: (itemId: string) => deleteOrderItem(orderId, itemId),
        onMutate: async (itemId) => {
            await queryClient.cancelQueries({ queryKey: detailKey });
            const previous = queryClient.getQueryData<Order>(detailKey);
            if (previous) {
                const optimistic = applyRemoveItemOptimistic(previous, itemId);
                queryClient.setQueryData(detailKey, optimistic);
            }
            return { previous } as { previous?: Order };
        },
        onError: (_error, _payload, context) => {
            if (context?.previous) {
                queryClient.setQueryData(detailKey, context.previous);
            }
        },
        onSuccess: (order) => {
            queryClient.setQueryData(detailKey, order);
            queryClient.invalidateQueries({ queryKey: ordersBaseKey });
        },
    });
}

export function useOrderCheckout(orderId: string | null, options?: { enabled?: boolean }) {
    const enabled = Boolean(orderId) && (options?.enabled ?? true);
    const key = orderId ? orderCheckoutKey(orderId) : [...ordersBaseKey, 'checkout', null] as const;
    return useQuery<OrderCheckoutResponse>({
        queryKey: key,
        queryFn: () => fetchOrderCheckout(orderId as string),
        enabled,
    });
}

export function useCreateSaleFromOrder() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ orderId, payload }: { orderId: string; payload: CreateSalePayload }) => createSaleFromOrder(orderId, payload),
        onSuccess: (data, variables) => {
            queryClient.setQueryData(orderCheckoutKey(variables.orderId), data);
            queryClient.setQueryData(orderDetailKey(variables.orderId), data.order);
        },
    });
}

export function usePayOrder() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ orderId, payload }: { orderId: string; payload: PayOrderPayload }) => payOrder(orderId, payload),
        onSuccess: (order) => {
            queryClient.setQueryData(orderDetailKey(order.id), order);
            queryClient.invalidateQueries({ queryKey: ordersBaseKey });
            queryClient.invalidateQueries({ queryKey: orderCheckoutKey(order.id) });
            queryClient.invalidateQueries({ queryKey: tablesKeys.status() });
            queryClient.invalidateQueries({ queryKey: cashKeys.base });
            queryClient.invalidateQueries({ queryKey: ['gestion', 'sales'] });
            queryClient.invalidateQueries({ queryKey: ['gestion', 'dashboard'] });
        },
    });
}

function applyOrderUpdateOptimistic(order: Order, payload: OrderUpdatePayload): Order {
    const tableIdProvided = 'table_id' in payload;
    const tableNameProvided = 'table_name' in payload;
    const customerProvided = 'customer_name' in payload;
    const noteProvided = 'note' in payload;
    const nextTableId = tableIdProvided ? payload.table_id ?? null : order.table_id;
    const normalizedTableName = tableNameProvided
        ? normalizeOptionalString(payload.table_name)
        : tableIdProvided && nextTableId === null
            ? ''
            : order.table_name;
    return {
        ...order,
        channel: payload.channel ?? order.channel,
        table_id: nextTableId,
        table_name: normalizedTableName,
        customer_name: customerProvided ? normalizeOptionalString(payload.customer_name) : order.customer_name,
        note: noteProvided ? normalizeOptionalString(payload.note) : order.note,
        updated_at: new Date().toISOString(),
    };
}

function applyAddItemOptimistic(order: Order, payload: OrderItemCreatePayload): Order {
    const quantity = payload.quantity ?? 0;
    const unitPrice = payload.unit_price ?? 0;
    const total = quantity * unitPrice;
    const normalizedName = payload.name ? payload.name.trim() : '';
    const optimisticItem = {
        id: `temp-${Date.now()}`,
        name: normalizedName || 'Producto',
        note: normalizeOptionalString(payload.note),
        quantity: quantity.toString(),
        unit_price: formatAmount(unitPrice),
        total_price: formatAmount(total),
        product_id: payload.product_id ?? null,
        modifiers: payload.modifiers ?? [],
        sold_without_stock: false,
    } satisfies Order['items'][number];
    return hydrateTotals(order, optimisticItem.total_price, (nextItems) => [...nextItems, optimisticItem]);
}

function applyUpdateItemOptimistic(order: Order, itemId: string, payload: OrderItemUpdatePayload): Order {
    const existing = order.items.find((item) => item.id === itemId);
    if (!existing) {
        return order;
    }
    const nextQuantity = payload.quantity ?? parseDecimal(existing.quantity);
    const nextUnitPrice = payload.unit_price ?? parseAmount(existing.unit_price);
    const nextTotal = nextQuantity * nextUnitPrice;
    const noteProvided = 'note' in payload;
    const nextItem = {
        ...existing,
        name: payload.name ?? existing.name,
        note: noteProvided ? normalizeOptionalString(payload.note) : existing.note,
        quantity: nextQuantity.toString(),
        unit_price: formatAmount(nextUnitPrice),
        total_price: formatAmount(nextTotal),
        product_id: 'product_id' in payload ? payload.product_id ?? null : existing.product_id,
        modifiers: payload.modifiers ?? existing.modifiers,
    } satisfies Order['items'][number];
    const delta = nextTotal - parseAmount(existing.total_price);
    return hydrateTotals(order, formatAmount(delta), (items) => items.map((item) => (item.id === itemId ? nextItem : item)));
}

function applyRemoveItemOptimistic(order: Order, itemId: string): Order {
    const existing = order.items.find((item) => item.id === itemId);
    if (!existing) {
        return order;
    }
    const delta = -parseAmount(existing.total_price);
    return hydrateTotals(order, formatAmount(delta), (items) => items.filter((item) => item.id !== itemId));
}

function hydrateTotals(order: Order, deltaRaw: string, updateItems: (items: Order['items']) => Order['items']): Order {
    const delta = parseAmount(deltaRaw);
    const nextSubtotal = Math.max(0, parseAmount(order.subtotal_amount) + delta);
    const nextTotal = Math.max(0, parseAmount(order.total_amount) + delta);
    return {
        ...order,
        items: updateItems(order.items),
        subtotal_amount: formatAmount(nextSubtotal),
        total_amount: formatAmount(nextTotal),
        updated_at: new Date().toISOString(),
    };
}

function parseAmount(value: string | number | undefined): number {
    if (typeof value === 'number') {
        return value;
    }
    const parsed = Number(value ?? 0);
    return Number.isNaN(parsed) ? 0 : parsed;
}

function parseDecimal(value: string | number | undefined): number {
    if (typeof value === 'number') {
        return value;
    }
    const parsed = Number(value ?? 0);
    return Number.isNaN(parsed) ? 0 : parsed;
}

function formatAmount(value: number): string {
    return value.toFixed(2);
}

function normalizeOptionalString(value: string | null | undefined): string {
    if (typeof value !== 'string') {
        return value ?? '';
    }
    return value.trim();
}
