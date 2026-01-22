import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { createOrder, fetchOrders, updateOrderStatus } from './api';
import type { OrderPayload, OrderStatus } from './types';

const ordersBaseKey = ['orders'];

export function useOrders(statusFilter: OrderStatus[]) {
    return useQuery({
        queryKey: [...ordersBaseKey, { statusFilter }],
        queryFn: () => fetchOrders({ status: statusFilter, limit: 100 }),
        refetchInterval: 15000,
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
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ordersBaseKey });
        },
    });
}
