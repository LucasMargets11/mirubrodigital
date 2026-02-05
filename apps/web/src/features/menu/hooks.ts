import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
    createMenuCategory,
    createMenuItem,
    deleteMenuCategory,
    deleteMenuItem,
    exportMenuWorkbook,
    fetchMenuStructure,
    importMenuWorkbook,
    getMenuBrandingSettings,
    getMenuQrCode,
    listMenuCategories,
    listMenuItems,
    updateMenuBrandingSettings,
    updateMenuCategory,
    updateMenuItem,
} from './api';
import type { MenuCategoryPayload, MenuItemFilters, MenuItemPayload } from './types';

const menuItemsRootKey = ['menu', 'items'];
const menuStructureKey = ['menu', 'structure'];

export const menuKeys = {
    categories: () => ['menu', 'categories'] as const,
    items: (filters: MenuItemFilters) => ['menu', 'items', filters] as const,
    structure: () => menuStructureKey as const,
    branding: () => ['menu', 'branding'] as const,
    qr: (businessId: number) => ['menu', 'qr', businessId] as const,
};

export function useMenuCategories() {
    return useQuery({
        queryKey: menuKeys.categories(),
        queryFn: () => listMenuCategories(),
    });
}

export function useMenuItems(filters: MenuItemFilters) {
    return useQuery({
        queryKey: menuKeys.items(filters),
        queryFn: () => listMenuItems(filters),
    });
}

export function useMenuStructure() {
    return useQuery({
        queryKey: menuKeys.structure(),
        queryFn: () => fetchMenuStructure(),
    });
}

export function useCreateMenuCategory() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: MenuCategoryPayload) => createMenuCategory(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: menuKeys.categories() });
            queryClient.invalidateQueries({ queryKey: menuItemsRootKey });
            queryClient.invalidateQueries({ queryKey: menuStructureKey });
        },
    });
}

export function useUpdateMenuCategory() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, payload }: { id: string; payload: Partial<MenuCategoryPayload> }) =>
            updateMenuCategory(id, payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: menuKeys.categories() });
            queryClient.invalidateQueries({ queryKey: menuItemsRootKey });
            queryClient.invalidateQueries({ queryKey: menuStructureKey });
        },
    });
}

export function useDeleteMenuCategory() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (id: string) => deleteMenuCategory(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: menuKeys.categories() });
            queryClient.invalidateQueries({ queryKey: menuItemsRootKey });
            queryClient.invalidateQueries({ queryKey: menuStructureKey });
        },
    });
}

export function useCreateMenuItem() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: MenuItemPayload) => createMenuItem(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: menuItemsRootKey });
            queryClient.invalidateQueries({ queryKey: menuKeys.categories() });
            queryClient.invalidateQueries({ queryKey: menuStructureKey });
        },
    });
}

export function useUpdateMenuItem() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, payload }: { id: string; payload: Partial<MenuItemPayload> }) =>
            updateMenuItem(id, payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: menuItemsRootKey });
            queryClient.invalidateQueries({ queryKey: menuKeys.categories() });
            queryClient.invalidateQueries({ queryKey: menuStructureKey });
        },
    });
}

export function useDeleteMenuItem() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (id: string) => deleteMenuItem(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: menuItemsRootKey });
            queryClient.invalidateQueries({ queryKey: menuKeys.categories() });
            queryClient.invalidateQueries({ queryKey: menuStructureKey });
        },
    });
}

export function useImportMenu() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (file: File) => importMenuWorkbook(file),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: menuKeys.categories() });
            queryClient.invalidateQueries({ queryKey: menuItemsRootKey });
            queryClient.invalidateQueries({ queryKey: menuStructureKey });
        },
    });
}

export function useExportMenu() {
    return useMutation({
        mutationFn: () => exportMenuWorkbook(),
    });
}

export function useMenuBrandingSettings() {
    return useQuery({
        queryKey: menuKeys.branding(),
        queryFn: () => getMenuBrandingSettings(),
    });
}

export function useUpdateMenuBrandingSettings() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: Parameters<typeof updateMenuBrandingSettings>[0]) => updateMenuBrandingSettings(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: menuKeys.branding() });
        },
    });
}

export function useMenuQrCode(businessId: number | null) {
    return useQuery({
        queryKey: menuKeys.qr(businessId || 0),
        queryFn: () => getMenuQrCode(businessId as number),
        enabled: !!businessId,
    });
}
