import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiError } from '@/lib/api/client';

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
    createQuote,
    fetchQuote,
    fetchQuotes,
    markQuoteAccepted,
    markQuoteRejected,
    markQuoteSent,
    updateQuote,
    fetchBusinessBillingProfile,
    updateBusinessBillingProfile,
    fetchBusinessBranding,
    updateBusinessBranding,
    uploadBusinessLogo,
    fetchDocumentSeries,
    createDocumentSeries,
    updateDocumentSeries,
    deleteDocumentSeries,
    setDocumentSeriesDefault,
} from './api';
import type {
    CommercialSettings,
    InventoryValuationFilters,
    ProductPayload,
    SalePayload,
    SalesFilters,
    StockMovementPayload,
    InventorySummaryStats,
    QuotePayload,
    QuotesFilters,
    BusinessBillingProfilePayload,
    BusinessBrandingPayload,
    DocumentSeriesPayload,
} from './types';

const productsBaseKey = ['gestion', 'products'];
const stockBaseKey = ['gestion', 'stock'];
const movementsBaseKey = ['gestion', 'movements'];
const salesBaseKey = ['gestion', 'sales'];
const quotesBaseKey = ['gestion', 'quotes'];
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

export function useSales(filters: SalesFilters, options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: [...salesBaseKey, { 
            search: filters.search,
            status: filters.status,
            payment_method: filters.payment_method,
            date_from: filters.date_from,
            date_to: filters.date_to,
        }],
        queryFn: () => fetchSales(filters),
        ...options,
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

type CommercialSettingsQueryOptions = {
    enabled?: boolean;
    skipIfForbidden?: boolean;
};

function isForbiddenError(error: unknown): error is ApiError {
    if (error instanceof ApiError) {
        return error.status === 403;
    }
    if (typeof error === 'object' && error !== null && 'status' in error) {
        return (error as { status?: number }).status === 403;
    }
    return false;
}

export function useCommercialSettingsQuery(options?: CommercialSettingsQueryOptions) {
    return useQuery<CommercialSettings | null>({
        queryKey: settingsBaseKey,
        queryFn: async () => {
            try {
                return await fetchCommercialSettings();
            } catch (error) {
                if (options?.skipIfForbidden && isForbiddenError(error)) {
                    return null;
                }
                throw error;
            }
        },
        enabled: options?.enabled ?? true,
        staleTime: 60_000,
        refetchOnWindowFocus: options?.skipIfForbidden ? false : undefined,
        retry: (failureCount, error) => {
            if (options?.skipIfForbidden && isForbiddenError(error)) {
                return false;
            }
            return failureCount < 3;
        },
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

// Quotes (Presupuestos)
export function useQuotes(filters: QuotesFilters) {
    return useQuery({
        queryKey: [...quotesBaseKey, {
            search: filters.search,
            status: filters.status,
            date_from: filters.date_from,
            date_to: filters.date_to,
            ordering: filters.ordering,
        }],
        queryFn: () => fetchQuotes(filters),
    });
}

export function useQuote(quoteId?: string) {
    return useQuery({
        queryKey: [...quotesBaseKey, quoteId],
        queryFn: () => fetchQuote(quoteId as string),
        enabled: Boolean(quoteId),
    });
}

export function useCreateQuote() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: QuotePayload) => createQuote(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: quotesBaseKey });
        },
    });
}

export function useUpdateQuote() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, payload }: { id: string; payload: Partial<QuotePayload> }) => updateQuote(id, payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: quotesBaseKey });
        },
    });
}

export function useMarkQuoteSent() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (quoteId: string) => markQuoteSent(quoteId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: quotesBaseKey });
        },
    });
}

export function useMarkQuoteAccepted() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (quoteId: string) => markQuoteAccepted(quoteId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: quotesBaseKey });
        },
    });
}

export function useMarkQuoteRejected() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (quoteId: string) => markQuoteRejected(quoteId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: quotesBaseKey });
        },
    });
}

// Business Configuration Hooks

const businessBillingProfileKey = ['businessBillingProfile'] as const;
const businessBrandingKey = ['businessBranding'] as const;
const documentSeriesKey = ['documentSeries'] as const;

export function useBusinessBillingProfileQuery() {
    return useQuery({
        queryKey: businessBillingProfileKey,
        queryFn: fetchBusinessBillingProfile,
        staleTime: 120_000,
    });
}

export function useUpdateBusinessBillingProfileMutation() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: BusinessBillingProfilePayload) => updateBusinessBillingProfile(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: businessBillingProfileKey });
        },
    });
}

export function useBusinessBrandingQuery() {
    return useQuery({
        queryKey: businessBrandingKey,
        queryFn: fetchBusinessBranding,
        staleTime: 120_000,
    });
}

export function useUpdateBusinessBrandingMutation() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: BusinessBrandingPayload) => updateBusinessBranding(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: businessBrandingKey });
        },
    });
}

export function useUploadBusinessLogoMutation() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ file, type }: { file: File; type: 'horizontal' | 'square' }) => uploadBusinessLogo(file, type),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: businessBrandingKey });
        },
    });
}

export function useDocumentSeriesQuery() {
    return useQuery({
        queryKey: documentSeriesKey,
        queryFn: fetchDocumentSeries,
        staleTime: 60_000,
    });
}

export function useCreateDocumentSeriesMutation() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: DocumentSeriesPayload) => createDocumentSeries(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: documentSeriesKey });
        },
    });
}

export function useUpdateDocumentSeriesMutation() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ seriesId, payload }: { seriesId: string; payload: Partial<DocumentSeriesPayload> }) =>
            updateDocumentSeries(seriesId, payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: documentSeriesKey });
        },
    });
}

export function useDeleteDocumentSeriesMutation() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (seriesId: string) => deleteDocumentSeries(seriesId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: documentSeriesKey });
        },
    });
}

export function useSetDocumentSeriesDefaultMutation() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (seriesId: string) => setDocumentSeriesDefault(seriesId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: documentSeriesKey });
        },
    });
}
