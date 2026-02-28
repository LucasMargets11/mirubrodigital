import { apiDelete, apiGet, apiGetBlob, apiPatch, apiPost } from '@/lib/api/client';

import type {
    CreateTipPreferenceResponse,
    MercadoPagoConnectionStatus,
    MenuBrandingSettings,
    MenuCategory,
    MenuCategoryPayload,
    MenuEngagementSettings,
    MenuEngagementSettingsPayload,
    MenuImportResult,
    MenuItem,
    MenuItemFilters,
    MenuItemPayload,
    MenuQrResponse,
    MenuStructureCategory,
    PublicMenuConfig,
    TipTransaction,
    TipVerifyResponse,
} from './types';

function buildQuery(params: Record<string, string | undefined>) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
            searchParams.append(key, value);
        }
    });
    const serialized = searchParams.toString();
    return serialized ? `?${serialized}` : '';
}

export function listMenuCategories() {
    return apiGet<MenuCategory[]>('/api/v1/menu/categories/');
}

export function createMenuCategory(payload: MenuCategoryPayload) {
    return apiPost<MenuCategory>('/api/v1/menu/categories/', payload);
}

export function updateMenuCategory(id: string, payload: Partial<MenuCategoryPayload>) {
    return apiPatch<MenuCategory>(`/api/v1/menu/categories/${id}/`, payload);
}

export function deleteMenuCategory(id: string) {
    return apiDelete<void>(`/api/v1/menu/categories/${id}/`);
}

export function listMenuItems(filters: MenuItemFilters = {}) {
    const query = buildQuery({
        category: filters.category ?? undefined,
        available: filters.available,
        search: filters.search,
    });
    return apiGet<MenuItem[]>(`/api/v1/menu/items/${query}`);
}

export function createMenuItem(payload: MenuItemPayload) {
    return apiPost<MenuItem>('/api/v1/menu/items/', payload);
}

export function updateMenuItem(id: string, payload: Partial<MenuItemPayload>) {
    return apiPatch<MenuItem>(`/api/v1/menu/items/${id}/`, payload);
}

export function deleteMenuItem(id: string) {
    return apiDelete<void>(`/api/v1/menu/items/${id}/`);
}

export function fetchMenuStructure() {
    return apiGet<MenuStructureCategory[]>('/api/v1/menu/structure/');
}

export function importMenuWorkbook(file: File) {
    const formData = new FormData();
    formData.append('file', file);
    return apiPost<MenuImportResult>('/api/v1/menu/import/', formData);
}

export function exportMenuWorkbook() {
    return apiGetBlob('/api/v1/menu/export/');
}

export function getPublicMenuConfig() {
    return apiGet<PublicMenuConfig>('/api/v1/menu/public/config/');
}

export function updatePublicMenuConfig(payload: Partial<PublicMenuConfig>) {
    return apiPatch<PublicMenuConfig>('/api/v1/menu/public/config/', payload);
}

export function uploadMenuLogo(file: File) {
    const formData = new FormData();
    formData.append('file', file);
    return apiPost<{ url: string }>('/api/v1/menu/public/logo/', formData);
}

export function getMenuBrandingSettings() {
    return apiGet<MenuBrandingSettings>('/api/v1/menu/branding/');
}

export function updateMenuBrandingSettings(payload: Partial<MenuBrandingSettings>) {
    return apiPatch<MenuBrandingSettings>('/api/v1/menu/branding/', payload);
}

export function getMenuQrCode(businessId: number) {
    return apiGet<MenuQrResponse>(`/api/v1/menu-qr/${businessId}/`);
}

export function uploadMenuItemImage(itemId: string, file: File) {
    const formData = new FormData();
    formData.append('file', file);
    return apiPost<{ image_url: string }>(`/api/v1/menu/items/${itemId}/image/`, formData);
}

export function deleteMenuItemImage(itemId: string) {
    return apiDelete<void>(`/api/v1/menu/items/${itemId}/image/`);
}

// ---------------------------------------------------------------------------
// Engagement: tips + reviews (admin panel)
// ---------------------------------------------------------------------------

export function getMenuEngagementSettings() {
    return apiGet<MenuEngagementSettings>('/api/v1/menu/engagement/');
}

export function updateMenuEngagementSettings(payload: MenuEngagementSettingsPayload) {
    return apiPatch<MenuEngagementSettings>('/api/v1/menu/engagement/', payload);
}

export function uploadEngagementQRImage(file: File) {
    const formData = new FormData();
    formData.append('file', file);
    return apiPost<{ url: string }>('/api/v1/menu/engagement/upload-qr/', formData);
}

// ---------------------------------------------------------------------------
// Mercado Pago OAuth per-business (Fase 2)
// ---------------------------------------------------------------------------

export function getMercadoPagoConnectionStatus() {
    return apiGet<MercadoPagoConnectionStatus>('/api/v1/menu/mercadopago/connect/status/');
}

export function startMercadoPagoOAuth() {
    return apiGet<{ auth_url: string }>('/api/v1/menu/mercadopago/connect/start/');
}

export function disconnectMercadoPago() {
    return apiDelete<{ detail: string }>('/api/v1/menu/mercadopago/connect/');
}

// ---------------------------------------------------------------------------
// Public: Tip preferences (Fase 2)
// ---------------------------------------------------------------------------

export function createPublicTipPreference(slug: string, amount: number, tableRef?: string) {
    return apiPost<CreateTipPreferenceResponse>(
        `/api/v1/menu/public/slug/${slug}/tips/create-preference/`,
        { amount, table_ref: tableRef ?? '' },
    );
}

export function getPublicTipStatus(tipId: string) {
    return apiGet<TipTransaction>(`/api/v1/menu/public/tips/${tipId}/status/`);
}

export function verifyPublicTip(tipId: string, paymentId: string) {
    return apiGet<TipVerifyResponse>(
        `/api/v1/menu/public/tips/${tipId}/verify/?payment_id=${encodeURIComponent(paymentId)}`,
    );
}
