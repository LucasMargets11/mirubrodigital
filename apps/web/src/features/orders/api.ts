import { apiDelete, apiGet, apiPatch, apiPost } from '@/lib/api/client';

import type {
    CloseOrderPayload,
    CreateSalePayload,
    KitchenItem,
    KitchenOrder,
    KitchenStatus,
    Order,
    OrderCheckoutResponse,
    OrderItemCreatePayload,
    OrderItemUpdatePayload,
    OrderPayload,
    OrderStartPayload,
    OrderStatus,
    OrderUpdatePayload,
    PayOrderPayload,
} from './types';

function buildQuery(params: Record<string, string | undefined>) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value && value.length > 0) {
            searchParams.append(key, value);
        }
    });
    const serialized = searchParams.toString();
    return serialized ? `?${serialized}` : '';
}

export function fetchOrders(params: { status?: OrderStatus[]; search?: string; limit?: number } = {}) {
    const query = buildQuery({
        status: params.status && params.status.length ? params.status.join(',') : undefined,
        search: params.search,
        limit: params.limit ? String(params.limit) : undefined,
    });
    return apiGet<Order[]>(`/api/v1/orders/${query}`);
}

export function fetchOrder(orderId: string) {
    return apiGet<Order>(`/api/v1/orders/${orderId}/`);
}

export function createOrder(payload: OrderPayload) {
    return apiPost<Order>('/api/v1/resto/orders/', payload);
}

export function startOrder(payload: OrderStartPayload) {
    return apiPost<Order>('/api/v1/orders/start/', payload);
}

export function createOrderItem(orderId: string, payload: OrderItemCreatePayload) {
    return apiPost<Order>(`/api/v1/orders/${orderId}/items/`, payload);
}

export function updateOrder(orderId: string, payload: OrderUpdatePayload) {
    return apiPatch<Order>(`/api/v1/orders/${orderId}/`, payload);
}

export function updateOrderItem(orderId: string, itemId: string, payload: OrderItemUpdatePayload) {
    return apiPatch<Order>(`/api/v1/orders/${orderId}/items/${itemId}/`, payload);
}

export function deleteOrderItem(orderId: string, itemId: string) {
    return apiDelete<Order>(`/api/v1/orders/${orderId}/items/${itemId}/`);
}

export function updateOrderStatus(orderId: string, status: OrderStatus) {
    return apiPost<Order>(`/api/v1/orders/${orderId}/status/`, { status });
}

export function closeOrder(orderId: string, payload: CloseOrderPayload) {
    return apiPost<Order>(`/api/v1/orders/${orderId}/close/`, payload);
}

export function cancelOrder(orderId: string) {
    return apiPost<Order>(`/api/v1/orders/${orderId}/cancel/`);
}

export function fetchOrderCheckout(orderId: string) {
    return apiGet<OrderCheckoutResponse>(`/api/v1/orders/${orderId}/checkout/`);
}

export function createSaleFromOrder(orderId: string, payload: CreateSalePayload) {
    return apiPost<OrderCheckoutResponse>(`/api/v1/orders/${orderId}/create-sale/`, payload);
}

export function payOrder(orderId: string, payload: PayOrderPayload) {
    return apiPost<Order>(`/api/v1/orders/${orderId}/pay/`, payload);
}

export function fetchKitchenBoard(params: { updated_after?: string; include_done?: boolean } = {}) {
    const query = new URLSearchParams();
    if (params.updated_after) query.append('updated_after', params.updated_after);
    if (params.include_done) query.append('include_done', 'true');
    const queryString = query.toString() ? `?${query.toString()}` : '';
    return apiGet<KitchenOrder[]>(`/api/v1/orders/kitchen/board/${queryString}`);
}

export function updateKitchenItemStatus(itemId: string, status: KitchenStatus) {
    return apiPatch<KitchenItem>(`/api/v1/orders/kitchen/items/${itemId}/`, { kitchen_status: status });
}

export function updateKitchenOrderBulk(orderId: string, status: KitchenStatus) {
    return apiPatch<KitchenOrder>(`/api/v1/orders/kitchen/orders/${orderId}/bulk/`, { kitchen_status: status });
}
