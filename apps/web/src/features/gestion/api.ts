import { apiGet, apiPatch, apiPost } from '@/lib/api/client';

import type { PaginatedResponse } from '@/types/api';
import type {
    InventoryValuationFilters,
    InventoryValuationResponse,
    Product,
    ProductPayload,
    ProductStock,
    Sale,
    SalePayload,
    SalesFilters,
    StockMovement,
    StockMovementPayload,
} from './types';

function buildQuery(params: Record<string, string | undefined>) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== '') {
            searchParams.append(key, value);
        }
    });
    const serialized = searchParams.toString();
    return serialized ? `?${serialized}` : '';
}

export function fetchProducts(params: { search?: string; includeInactive?: boolean } = {}) {
    const query = buildQuery({
        search: params.search,
        include_inactive: params.includeInactive ? 'true' : undefined,
    });
    return apiGet<Product[]>(`/api/v1/catalog/products/${query}`);
}

export function createProduct(payload: ProductPayload) {
    return apiPost<Product>('/api/v1/catalog/products/', payload);
}

export function updateProduct(productId: string, payload: Partial<ProductPayload>) {
    return apiPatch<Product>(`/api/v1/catalog/products/${productId}/`, payload);
}

export function fetchStockLevels(params: { search?: string; status?: string } = {}) {
    const query = buildQuery({ search: params.search, status: params.status });
    return apiGet<ProductStock[]>(`/api/v1/inventory/stock/${query}`);
}

export function fetchStockMovements(params: { product_id?: string; limit?: number } = {}) {
    const query = buildQuery({
        product_id: params.product_id,
        limit: params.limit ? String(params.limit) : undefined,
    });
    return apiGet<StockMovement[]>(`/api/v1/inventory/movements/${query}`);
}

export function createMovement(payload: StockMovementPayload) {
    return apiPost<StockMovement>('/api/v1/inventory/movements/', payload);
}

export function fetchSales(params: SalesFilters = {}) {
    const query = buildQuery({
        search: params.search,
        status: params.status,
        payment_method: params.payment_method,
        date_from: params.date_from,
        date_to: params.date_to,
    });
    return apiGet<PaginatedResponse<Sale>>(`/api/v1/sales/${query}`);
}

export function fetchSale(saleId: string) {
    return apiGet<Sale>(`/api/v1/sales/${saleId}/`);
}

export function createSale(payload: SalePayload) {
    return apiPost<Sale>('/api/v1/sales/', payload);
}

export function fetchInventoryValuation(params: InventoryValuationFilters = {}) {
    const activeParam = params.active ?? 'true';
    const query = buildQuery({
        q: params.search,
        status: params.status,
        sort: params.sort,
        only_in_stock: params.onlyInStock ? 'true' : undefined,
        active: activeParam === 'all' ? undefined : activeParam,
    });
    return apiGet<InventoryValuationResponse>(`/api/v1/inventory/valuation/${query}`);
}
