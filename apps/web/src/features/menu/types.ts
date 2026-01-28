export type MenuCategory = {
    id: string;
    name: string;
    description: string;
    position: number;
    is_active: boolean;
    item_count: number;
};

export type MenuCategoryPayload = {
    name: string;
    description?: string;
    position?: number;
    is_active?: boolean;
};

export type MenuItem = {
    id: string;
    category_id: string | null;
    category_name: string | null;
    name: string;
    description: string;
    price: string;
    sku: string;
    tags: string[];
    is_available: boolean;
    is_featured: boolean;
    position: number;
    estimated_time_minutes: number;
};

export type MenuItemPayload = {
    category_id?: string | null;
    name: string;
    description?: string;
    price?: number;
    sku?: string;
    tags?: string[];
    is_available?: boolean;
    is_featured?: boolean;
    position?: number;
    estimated_time_minutes?: number;
};

export type MenuItemFilters = {
    category?: string | null;
    available?: 'true' | 'false';
    search?: string;
};

export type MenuStructureItem = {
    id: string;
    name: string;
    description: string;
    price: string;
    tags: string[];
    is_available: boolean;
    is_featured: boolean;
    position: number;
};

export type MenuStructureCategory = {
    id: string;
    name: string;
    description: string;
    position: number;
    items: MenuStructureItem[];
};

export type MenuImportSummary = {
    total_rows: number;
    created_categories: number;
    updated_categories: number;
    created_items: number;
    updated_items: number;
    skipped_rows: number;
};

export type MenuImportPreview = {
    line_number: number;
    category: string;
    name: string;
    price: string;
    action: string;
    available: boolean;
};

export type MenuImportResult = {
    summary: MenuImportSummary;
    preview: MenuImportPreview[];
};
