import { apiGet, apiPost } from '@/lib/api/client';

import type { InventoryImportJob, InventoryImportPreviewResponse } from './types';

export function uploadInventoryImport(file: File) {
    const formData = new FormData();
    formData.append('file', file);
    return apiPost<InventoryImportJob>('/api/v1/inventory/imports/', formData);
}

export function previewInventoryImport(importId: string) {
    return apiPost<InventoryImportPreviewResponse>(`/api/v1/inventory/imports/${importId}/preview/`);
}

export function applyInventoryImport(importId: string) {
    return apiPost<InventoryImportJob>(`/api/v1/inventory/imports/${importId}/apply/`);
}

export function getInventoryImport(importId: string) {
    return apiGet<InventoryImportJob>(`/api/v1/inventory/imports/${importId}/`);
}
