import { apiGet, apiPost } from '@/lib/api/client';

import type { Order, OrderPayload, OrderStatus } from './types';

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

export function createOrder(payload: OrderPayload) {
    return apiPost<Order>('/api/v1/orders/', payload);
}

export function updateOrderStatus(orderId: string, status: OrderStatus) {
    return apiPost<Order>(`/api/v1/orders/${orderId}/status/`, { status });
}
