import { apiGet, apiPost, apiPut } from '@/lib/api/client';

import type { Order } from '@/features/orders/types';

import type {
    Table,
    TableConfiguration,
    TableConfigurationPayload,
    TableStatusMap,
    TablesLayout,
    TablesMapStateResponse,
} from './types';

export type TableStatusResponse = {
    statuses: TableStatusMap;
    generated_at: string;
};

export function fetchTables() {
    return apiGet<Table[]>('/api/v1/resto/tables/');
}

export function fetchTablesLayout() {
    return apiGet<TablesLayout>('/api/v1/resto/tables/layout/');
}

export function fetchTableStatuses() {
    return apiGet<TableStatusResponse>('/api/v1/resto/tables/status/');
}

export function fetchRestaurantTablesSnapshot() {
    return apiGet('/api/v1/restaurant/tables/');
}

export function fetchRestaurantTablesMapState() {
    return apiGet<TablesMapStateResponse>('/api/v1/restaurant/tables/map-state/');
}

export function assignOrderTable(orderId: string, tableId: string) {
    return apiPost<Order>(`/api/v1/resto/orders/${orderId}/table/`, { table_id: tableId });
}

export function fetchTableConfiguration() {
    return apiGet<TableConfiguration>('/api/v1/resto/tables/config/');
}

export function saveTableConfiguration(payload: TableConfigurationPayload) {
    return apiPut<TableConfiguration>('/api/v1/resto/tables/config/', payload);
}
