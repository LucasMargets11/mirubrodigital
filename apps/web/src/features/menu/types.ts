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

export type LayoutTheme = {
  primary: string
  secondary: string
  background: string
  text: string
  mutedText?: string
  accent?: string
  divider?: string
  fontFamily?: string
  headingFont?: string
  bodyFont?: string
  menuHeadingFontSize?: number
  menuBodyFontSize?: number
  menuLogoUrl?: string
  menuLogoPosition?: 'top_center' | 'title_left' | 'top_right_small' | 'watermark'
  menuLogoSize?: 'sm' | 'md' | 'lg'
  menuLogoWatermarkOpacity?: number
}

export type PublicMenuConfig = {
  enabled: boolean
  slug: string
  public_id: string
  brand_name: string
  logo_url: string | null
  theme_json: LayoutTheme
  template_key: string
  updated_at: string
}

export type PublicMenuItem = Pick<MenuItem, 'id' | 'name' | 'description' | 'price' | 'is_available' | 'tags' | 'sku'>

export type PublicMenuCategory = Pick<MenuCategory, 'id' | 'name' | 'description' | 'position'> & {
  items: PublicMenuItem[]
}

export type PublicMenuResponse = {
  business_name: string
  config: PublicMenuConfig
  categories: PublicMenuCategory[]
}

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
