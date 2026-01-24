export type InventoryImportStatus = 'pending' | 'processing' | 'done' | 'failed';

export type InventoryImportAction = 'create' | 'update';
export type InventoryImportStockAction = 'adjust' | 'skip';
export type InventoryImportRowStatus = 'ok' | 'warning' | 'error';

export type InventoryImportSummary = {
    total_rows: number;
    create_count: number;
    update_count: number;
    adjust_count: number;
    skip_count: number;
    warning_count: number;
    error_count: number;
};

export type InventoryImportPreviewRow = {
    line_number: number;
    name: string;
    sku?: string | null;
    action: InventoryImportAction;
    stock_action: InventoryImportStockAction;
    status: InventoryImportRowStatus;
    messages: string[];
    values?: Record<string, string | number | null>;
};

export type InventoryImportPreviewResponse = {
    summary: InventoryImportSummary;
    rows: InventoryImportPreviewRow[];
};

export type InventoryImportJob = {
    id: string;
    filename: string;
    status: InventoryImportStatus;
    created_at: string;
    updated_at: string;
    summary?: InventoryImportSummary | null;
    created_count: number;
    updated_count: number;
    adjusted_count: number;
    skipped_count: number;
    error_count: number;
    warning_count?: number;
    result_url?: string | null;
    errors?: string[] | null;
};
