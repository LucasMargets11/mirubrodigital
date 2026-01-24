import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
    createMovement,
    createProduct,
    createSale,
    fetchCommercialSettings,
    fetchInventorySummary,
    fetchInventoryValuation,
    fetchLowStockAlerts,
    fetchOutOfStockAlerts,
    fetchProducts,
    fetchRecentInventoryMovements,
    fetchRecentSales,
    fetchSale,
    fetchSales,
    fetchSalesTodaySummary,
    fetchStockLevels,
    fetchStockMovements,
    fetchTopSellingProducts,
    updateCommercialSettings,
    updateProduct,
} from './api';
import type {
    CommercialSettings,
    InventoryValuationFilters,
    ProductPayload,
    SalePayload,
    SalesFilters,
    StockMovementPayload,
    InventorySummaryStats,
} from './types';

const productsBaseKey = ['gestion', 'products'];
const stockBaseKey = ['gestion', 'stock'];
const movementsBaseKey = ['gestion', 'movements'];
const salesBaseKey = ['gestion', 'sales'];
const valuationBaseKey = ['gestion', 'inventory', 'valuation'];
const dashboardBaseKey = ['gestion', 'dashboard'];
const settingsBaseKey = ['gestion', 'commercial-settings'];

export function useProducts(search: string, includeInactive: boolean, options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: [...productsBaseKey, { search, includeInactive }],
        queryFn: () => fetchProducts({ search, includeInactive }),
        enabled: options?.enabled ?? true,
    });
}

export function useCreateProduct() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: ProductPayload) => createProduct(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: productsBaseKey });
            queryClient.invalidateQueries({ queryKey: stockBaseKey });
            queryClient.invalidateQueries({ queryKey: valuationBaseKey });
        },
    });
}

export function useUpdateProduct() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, payload }: { id: string; payload: Partial<ProductPayload> }) => updateProduct(id, payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: productsBaseKey });
            queryClient.invalidateQueries({ queryKey: stockBaseKey });
            queryClient.invalidateQueries({ queryKey: valuationBaseKey });
        },
    });
}

export function useStockLevels(search: string, status: string) {
    return useQuery({
        queryKey: [...stockBaseKey, { search, status }],
        queryFn: () => fetchStockLevels({ search, status }),
    });
}

export function useStockMovements(productId?: string) {
    return useQuery({
        queryKey: [...movementsBaseKey, { productId }],
        queryFn: () => fetchStockMovements({ product_id: productId, limit: 50 }),
    });
}

export function useCreateMovement() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: StockMovementPayload) => createMovement(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: stockBaseKey });
            queryClient.invalidateQueries({ queryKey: movementsBaseKey });
            queryClient.invalidateQueries({ queryKey: valuationBaseKey });
        },
    });
}

export function useSales(filters: SalesFilters) {
    return useQuery({
        queryKey: [...salesBaseKey, filters],
        queryFn: () => fetchSales(filters),
    });
}

export function useSale(saleId?: string) {
    return useQuery({
        queryKey: [...salesBaseKey, saleId],
        queryFn: () => fetchSale(saleId as string),
        enabled: Boolean(saleId),
    });
}

export function useCreateSale() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: SalePayload) => createSale(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: salesBaseKey });
            queryClient.invalidateQueries({ queryKey: stockBaseKey });
            queryClient.invalidateQueries({ queryKey: movementsBaseKey });
            queryClient.invalidateQueries({ queryKey: valuationBaseKey });
        },
    });
}

export function useInventoryValuation(filters: InventoryValuationFilters) {
    return useQuery({
        queryKey: [...valuationBaseKey, filters],
        queryFn: () => fetchInventoryValuation(filters),
    });
}

export function useInventorySummary(options?: { initialData?: InventorySummaryStats | null; enabled?: boolean }) {
    return useQuery({
        queryKey: [...dashboardBaseKey, 'inventory-summary'],
        queryFn: () => fetchInventorySummary(),
        enabled: options?.enabled ?? true,
        initialData: options?.initialData ?? undefined,
        staleTime: 60_000,
    });
}

export function useLowStockPreview(limit = 5, enabled = true) {
    return useQuery({
        queryKey: [...dashboardBaseKey, 'low-stock', { limit }],
        queryFn: () => fetchLowStockAlerts({ limit, ordering: 'qty' }),
        enabled,
        staleTime: 60_000,
    });
}

export function useOutOfStockPreview(limit = 5, enabled = true) {
    return useQuery({
        queryKey: [...dashboardBaseKey, 'out-of-stock', { limit }],
        queryFn: () => fetchOutOfStockAlerts({ limit, ordering: 'qty' }),
        enabled,
        staleTime: 60_000,
    });
}

export function useRecentInventoryMovements(limit = 5, enabled = true) {
    return useQuery({
        queryKey: [...dashboardBaseKey, 'movements', { limit }],
        queryFn: () => fetchRecentInventoryMovements(limit),
        enabled,
        staleTime: 60_000,
    });
}

export function useSalesTodaySummary(enabled = true) {
    return useQuery({
        queryKey: [...dashboardBaseKey, 'sales-today'],
        queryFn: () => fetchSalesTodaySummary(),
        enabled,
        staleTime: 60_000,
    });
}

export function useRecentSales(limit = 5, enabled = true) {
    return useQuery({
        queryKey: [...dashboardBaseKey, 'recent-sales', { limit }],
        queryFn: () => fetchRecentSales(limit),
        enabled,
        staleTime: 60_000,
    });
}

export function useTopSellingProducts(range = '7d', limit = 5, enabled = true) {
    return useQuery({
        queryKey: [...dashboardBaseKey, 'top-products', { range, limit }],
        queryFn: () => fetchTopSellingProducts({ range, limit }),
        enabled,
        staleTime: 120_000,
    });
}

export function useCommercialSettingsQuery(options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: settingsBaseKey,
        queryFn: () => fetchCommercialSettings(),
        enabled: options?.enabled ?? true,
        staleTime: 60_000,
    });
}

export function useUpdateCommercialSettingsMutation() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: Partial<CommercialSettings>) => updateCommercialSettings(payload),
        onMutate: async (payload) => {
            await queryClient.cancelQueries({ queryKey: settingsBaseKey });
            const previous = queryClient.getQueryData<CommercialSettings>(settingsBaseKey);
            queryClient.setQueryData<CommercialSettings>(settingsBaseKey, (current) => ({
                ...(current ?? ({} as CommercialSettings)),
                ...payload,
            }));
            return { previous };
        },
        onError: (_error, _payload, context) => {
            if (context?.previous) {
                queryClient.setQueryData(settingsBaseKey, context.previous);
            }
        },
        onSuccess: (data) => {
            queryClient.setQueryData(settingsBaseKey, data);
        },
        onSettled: () => {
            queryClient.invalidateQueries({ queryKey: settingsBaseKey });
        },
    });
}
