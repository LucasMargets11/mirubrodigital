'use client';

import { useState } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { fetchKitchenBoard, updateKitchenItemStatus, updateKitchenOrderBulk } from '@/features/orders/api';
import type { KitchenStatus } from '@/features/orders/types';

import { KitchenBoard } from './components/kitchen-board';
import { KitchenHero } from './components/kitchen-hero';

export function KitchenView() {
    const [autoRefresh, setAutoRefresh] = useState(true);
    const queryClient = useQueryClient();

    const {
        data: orders,
        isLoading,
        isError,
        dataUpdatedAt,
        refetch,
        isRefetching,
    } = useQuery({
        queryKey: ['kitchen-board'],
        queryFn: () => fetchKitchenBoard(),
        refetchInterval: autoRefresh ? 3000 : false,
        refetchOnWindowFocus: true,
    });

    const updateItemMutation = useMutation({
        mutationFn: ({ itemId, status }: { itemId: string; status: KitchenStatus }) =>
            updateKitchenItemStatus(itemId, status),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['kitchen-board'] });
        },
    });

    const updateOrderMutation = useMutation({
        mutationFn: ({ orderId, status }: { orderId: string; status: KitchenStatus }) =>
            updateKitchenOrderBulk(orderId, status),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['kitchen-board'] });
        },
    });

    const metrics = {
        pending: 0,
        inProgress: 0,
        ready: 0,
    };

    if (orders) {
        orders.forEach((o) => {
            o.items.forEach((i) => {
                if (i.kitchen_status === 'pending') metrics.pending++;
                if (i.kitchen_status === 'in_progress') metrics.inProgress++;
                if (i.kitchen_status === 'ready') metrics.ready++;
            });
        });
    }

    return (
        <div className="flex h-[calc(100vh-6rem)] flex-col gap-4 p-4 lg:p-6">
            <KitchenHero
                metrics={metrics}
                isConnected={!isError}
                isUpdating={isRefetching || isLoading}
                lastUpdated={dataUpdatedAt ? new Date(dataUpdatedAt) : undefined}
                onRefresh={refetch}
                autoRefresh={autoRefresh}
                toggleAutoRefresh={() => setAutoRefresh(!autoRefresh)}
            />

            {isLoading && !orders ? (
                <div className="flex h-full items-center justify-center text-slate-400">
                    Cargando tablero...
                </div>
            ) : (
                <KitchenBoard
                    orders={orders || []}
                    onUpdateItem={(id, status) => updateItemMutation.mutate({ itemId: id, status })}
                    onUpdateOrder={(id, status) => updateOrderMutation.mutate({ orderId: id, status })}
                />
            )}
        </div>
    );
}
