import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiError } from '@/lib/api/client';

import {
    assignOrderTable,
    fetchRestaurantTablesMapState,
    fetchTableConfiguration,
    fetchTableStatuses,
    fetchTables,
    fetchTablesLayout,
    saveTableConfiguration,
} from './api';
import type { TableConfigurationPayload } from './types';

export const tablesKeys = {
    list: () => ['tables', 'list'] as const,
    layout: () => ['tables', 'layout'] as const,
    status: () => ['tables', 'status'] as const,
    config: () => ['tables', 'config'] as const,
    mapState: () => ['tables', 'map-state'] as const,
};

export function useTables(enabled = true) {
    return useQuery({
        queryKey: tablesKeys.list(),
        queryFn: () => fetchTables(),
        enabled,
    });
}

export function useTablesLayout(enabled = true) {
    return useQuery({
        queryKey: tablesKeys.layout(),
        queryFn: () => fetchTablesLayout(),
        enabled,
    });
}

export function useTablesStatus(enabled = true, refetchInterval = 4000) {
    return useQuery({
        queryKey: tablesKeys.status(),
        queryFn: () => fetchTableStatuses(),
        enabled,
        refetchInterval: enabled ? refetchInterval : false,
    });
}

export function useAssignOrderTable() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ orderId, tableId }: { orderId: string; tableId: string }) => assignOrderTable(orderId, tableId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: tablesKeys.status() });
            queryClient.invalidateQueries({ queryKey: tablesKeys.mapState() });
            queryClient.invalidateQueries({ queryKey: ['orders'] });
        },
    });
}

export function useRestaurantTablesMapState(options?: { enabled?: boolean; refetchInterval?: number }) {
    const enabled = options?.enabled ?? true;
    const refetchInterval = options?.refetchInterval ?? 6000;
    return useQuery({
        queryKey: tablesKeys.mapState(),
        queryFn: () => fetchRestaurantTablesMapState(),
        enabled,
        staleTime: 2000,
        refetchInterval: enabled ? refetchInterval : false,
        retry: (failureCount, error) => {
            if (error instanceof ApiError && error.status === 403) {
                return false;
            }
            return failureCount < 2;
        },
    });
}

export function useTableConfiguration() {
    return useQuery({
        queryKey: tablesKeys.config(),
        queryFn: () => fetchTableConfiguration(),
    });
}

export function useSaveTableConfiguration() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: TableConfigurationPayload) => saveTableConfiguration(payload),
        onSuccess: (data) => {
            queryClient.setQueryData(tablesKeys.config(), data);
            queryClient.invalidateQueries({ queryKey: tablesKeys.list() });
            queryClient.invalidateQueries({ queryKey: tablesKeys.layout() });
            queryClient.invalidateQueries({ queryKey: tablesKeys.status() });
            queryClient.invalidateQueries({ queryKey: tablesKeys.mapState() });
        },
    });
}
