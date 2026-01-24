import { useMutation, useQuery } from '@tanstack/react-query';

import { applyInventoryImport, getInventoryImport, previewInventoryImport, uploadInventoryImport } from './api';
import type { InventoryImportJob, InventoryImportPreviewResponse } from './types';

export function useUploadInventoryImport() {
    return useMutation({
        mutationFn: (file: File) => uploadInventoryImport(file),
    });
}

export function usePreviewInventoryImport() {
    return useMutation({
        mutationFn: (importId: string) => previewInventoryImport(importId),
    });
}

export function useApplyInventoryImport() {
    return useMutation({
        mutationFn: (importId: string) => applyInventoryImport(importId),
    });
}

export function useInventoryImport(importId?: string, options?: { enabled?: boolean; refetchInterval?: number | false }) {
    return useQuery<InventoryImportJob>({
        queryKey: ['inventory-imports', importId],
        queryFn: () => getInventoryImport(importId as string),
        enabled: Boolean(importId) && (options?.enabled ?? true),
        refetchInterval: options?.refetchInterval,
    });
}

export function useImportPreviewRows(preview?: InventoryImportPreviewResponse) {
    return preview?.rows ?? [];
}
