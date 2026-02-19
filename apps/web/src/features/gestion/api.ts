import { apiGet, apiPatch, apiPost, apiDelete } from '@/lib/api/client';

import type { PaginatedResponse } from '@/types/api';
import type {
    InventorySummaryStats,
    InventoryValuationFilters,
    InventoryValuationResponse,
    Product,
    ProductPayload,
    ProductStock,
    Sale,
    SalePayload,
    SaleTimelineItem,
    SalesFilters,
    SalesTodaySummary,
    StockMovement,
    StockMovementPayload,
    TopProductMetric,
    CommercialSettings,
    Quote,
    QuotePayload,
    QuotesFilters,
    BusinessBillingProfile,
    BusinessBillingProfilePayload,
    BusinessBranding,
    BusinessBrandingPayload,
    DocumentSeries,
    DocumentSeriesPayload,
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

export function fetchInventorySummary() {
    return apiGet<InventorySummaryStats>('/api/v1/inventory/summary/');
}

export function fetchLowStockAlerts(params: { limit?: number; ordering?: 'qty' | 'name' } = {}) {
    const query = buildQuery({
        limit: params.limit ? String(params.limit) : undefined,
        ordering: params.ordering === 'qty' ? 'qty' : undefined,
    });
    return apiGet<ProductStock[]>(`/api/v1/inventory/low-stock/${query}`);
}

export function fetchOutOfStockAlerts(params: { limit?: number; ordering?: 'qty' | 'name' } = {}) {
    const query = buildQuery({
        limit: params.limit ? String(params.limit) : undefined,
        ordering: params.ordering === 'qty' ? 'qty' : undefined,
    });
    return apiGet<ProductStock[]>(`/api/v1/inventory/out-of-stock/${query}`);
}

export function fetchRecentInventoryMovements(limit = 5) {
    const query = buildQuery({ limit: limit ? String(limit) : undefined });
    return apiGet<StockMovement[]>(`/api/v1/inventory/movements/recent/${query}`);
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

export function fetchSalesTodaySummary() {
    return apiGet<SalesTodaySummary>('/api/v1/sales/summary/today/');
}

export function fetchRecentSales(limit = 5) {
    const query = buildQuery({ limit: limit ? String(limit) : undefined });
    return apiGet<SaleTimelineItem[]>(`/api/v1/sales/recent/${query}`);
}

export function fetchTopSellingProducts(params: { range?: string; limit?: number } = {}) {
    const query = buildQuery({
        range: params.range,
        limit: params.limit ? String(params.limit) : undefined,
    });
    return apiGet<{ range_days: number; items: TopProductMetric[] }>(`/api/v1/sales/top-products/${query}`);
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

export function fetchCommercialSettings() {
    return apiGet<CommercialSettings>('/api/v1/commercial/settings/');
}

export function updateCommercialSettings(payload: Partial<CommercialSettings>) {
    return apiPatch<CommercialSettings>('/api/v1/commercial/settings/', payload);
}

// Quotes (Presupuestos)
export function fetchQuotes(params: QuotesFilters = {}) {
    const query = buildQuery({
        search: params.search,
        status: params.status,
        date_from: params.date_from,
        date_to: params.date_to,
        ordering: params.ordering,
    });
    return apiGet<PaginatedResponse<Quote>>(`/api/v1/sales/quotes/${query}`);
}

export function fetchQuote(quoteId: string) {
    return apiGet<Quote>(`/api/v1/sales/quotes/${quoteId}/`);
}

export function createQuote(payload: QuotePayload) {
    return apiPost<Quote>('/api/v1/sales/quotes/', payload);
}

export function updateQuote(quoteId: string, payload: Partial<QuotePayload>) {
    return apiPatch<Quote>(`/api/v1/sales/quotes/${quoteId}/`, payload);
}

export function markQuoteSent(quoteId: string) {
    return apiPost<Quote>(`/api/v1/sales/quotes/${quoteId}/mark-sent/`, {});
}

export function markQuoteAccepted(quoteId: string) {
    return apiPost<Quote>(`/api/v1/sales/quotes/${quoteId}/mark-accepted/`, {});
}

export function markQuoteRejected(quoteId: string) {
    return apiPost<Quote>(`/api/v1/sales/quotes/${quoteId}/mark-rejected/`, {});
}

export function getQuotePdfUrl(quoteId: string): string {
    return `/api/v1/sales/quotes/${quoteId}/pdf/`;
}

// Business Configuration APIs

export function fetchBusinessBillingProfile() {
    return apiGet<BusinessBillingProfile>('/api/v1/settings/billing/');
}

export function updateBusinessBillingProfile(payload: BusinessBillingProfilePayload) {
    return apiPatch<BusinessBillingProfile>('/api/v1/settings/billing/', payload);
}

export function fetchBusinessBranding() {
    return apiGet<BusinessBranding>('/api/v1/settings/branding/');
}

export function updateBusinessBranding(payload: BusinessBrandingPayload) {
    return apiPatch<BusinessBranding>('/api/v1/settings/branding/', payload);
}

export function uploadBusinessLogo(file: File, type: 'horizontal' | 'square') {
    const formData = new FormData();
    const fieldName = type === 'horizontal' ? 'logo_horizontal' : 'logo_square';
    formData.append(fieldName, file);
    return apiPatch<BusinessBranding>('/api/v1/settings/branding/', formData);
}

export function fetchDocumentSeries() {
    return apiGet<DocumentSeries[]>('/api/v1/invoices/document-series/');
}

export function createDocumentSeries(payload: DocumentSeriesPayload) {
    return apiPost<DocumentSeries>('/api/v1/invoices/document-series/', payload);
}

export function updateDocumentSeries(seriesId: string, payload: Partial<DocumentSeriesPayload>) {
    return apiPatch<DocumentSeries>(`/api/v1/invoices/document-series/${seriesId}/`, payload);
}

export function deleteDocumentSeries(seriesId: string) {
    return apiDelete<void>(`/api/v1/invoices/document-series/${seriesId}/`);
}

export function setDocumentSeriesDefault(seriesId: string) {
    return apiPost<DocumentSeries>(`/api/v1/invoices/document-series/${seriesId}/set-default/`, {});
}

export function fetchBusinessEntitlements() {
    return apiGet<{
        entitlements: string[];
        plan: {
            plan: string;
            status: string;
            max_branches: number;
            max_seats: number;
            effective_max_branches: number;
            effective_max_seats: number;
        };
        addons: Array<{
            code: string;
            quantity: number;
            is_active: boolean;
        }>;
    }>('/api/v1/business/entitlements/');
}
