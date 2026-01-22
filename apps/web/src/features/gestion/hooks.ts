import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
    createMovement,
    createProduct,
    createSale,
    fetchInventoryValuation,
    fetchProducts,
    fetchSale,
    fetchSales,
    fetchStockLevels,
    fetchStockMovements,
    updateProduct,
} from './api';
import type {
    InventoryValuationFilters,
    ProductPayload,
    SalePayload,
    SalesFilters,
    StockMovementPayload,
} from './types';

const productsBaseKey = ['gestion', 'products'];
const stockBaseKey = ['gestion', 'stock'];
const movementsBaseKey = ['gestion', 'movements'];
const salesBaseKey = ['gestion', 'sales'];
const valuationBaseKey = ['gestion', 'inventory', 'valuation'];

export function useProducts(search: string, includeInactive: boolean) {
    return useQuery({
        queryKey: [...productsBaseKey, { search, includeInactive }],
        queryFn: () => fetchProducts({ search, includeInactive }),
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
