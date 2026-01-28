import { apiDelete, apiGet, apiGetBlob, apiPatch, apiPost } from '@/lib/api/client';

import type {
    MenuCategory,
    MenuCategoryPayload,
    MenuImportResult,
    MenuItem,
    MenuItemFilters,
    MenuItemPayload,
    MenuStructureCategory,
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
