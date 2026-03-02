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
    image_url: string | null;
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

export type PublicMenuItem = Pick<MenuItem, 'id' | 'name' | 'description' | 'price' | 'is_available' | 'tags' | 'sku'> & {
  image_url: string | null
}

export type PublicMenuCategory = Pick<MenuCategory, 'id' | 'name' | 'description' | 'position'> & {
  items: PublicMenuItem[]
}

export type PublicMenuResponse = {
    business: {
        id: number
        name: string
    }
    slug: string
    public_url: string
    config: PublicMenuConfig
    branding: MenuBrandingSettings
    categories: PublicMenuCategory[]
    layout_blocks: PublicMenuLayoutBlock[]
    engagement: PublicMenuEngagement
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
    image_url: string | null;
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

export type MenuBrandingSettings = {
    display_name: string;
    logo_url: string | null;
    palette_primary: string;
    palette_secondary: string;
    palette_background: string;
    palette_text: string;
    font_heading: string;
    font_body: string;
    font_scale_heading: number;
    font_scale_body: number;
    updated_at: string;
};

export type MenuQrResponse = {
    business_id: number;
    slug: string;
    public_url: string;
    qr_svg: string;
    generated_at: string;
};

// ---------------------------------------------------------------------------
// Engagement: tips + reviews
// ---------------------------------------------------------------------------

export type TipsMode = 'mp_link' | 'mp_qr_image' | 'mp_oauth_checkout';

export type MenuEngagementSettings = {
    tips_enabled: boolean;
    tips_mode: TipsMode;
    mp_tip_url: string | null;
    mp_qr_image: File | null; // write-only (upload)
    mp_qr_image_url: string | null;
    reviews_enabled: boolean;
    google_place_id: string | null;
    google_review_url: string | null;
    google_write_review_url: string | null;
    updated_at: string;
};

export type MenuEngagementSettingsPayload = Partial<Omit<MenuEngagementSettings, 'mp_qr_image' | 'mp_qr_image_url' | 'google_write_review_url' | 'updated_at'>>;

/** Safe public engagement data returned inside PublicMenuResponse. Never contains tokens. */
export type PublicMenuEngagement = {
    tips_enabled: boolean;
    tips_mode: TipsMode;
    mp_tip_url: string | null;
    mp_qr_image_url: string | null;
    reviews_enabled: boolean;
    google_write_review_url: string | null;
};

export type MercadoPagoConnectionStatus = {
    connected: boolean;
    status: 'connected' | 'expired' | 'revoked' | 'error' | null;
    mp_user_id: string | null;
    updated_at: string | null;
};

export type TipTransaction = {
    id: string;
    amount: string;
    currency: string;
    status: 'created' | 'pending' | 'approved' | 'rejected' | 'cancelled';
    external_reference: string;
    created_at: string;
};

export type TipVerifyResponse = {
    tip_id: string;
    status: 'created' | 'pending' | 'approved' | 'rejected' | 'cancelled';
    mp_payment_id: string | null;
    amount: string;
    currency: string;
    mp_status: string;
    mp_status_detail: string;
    verified_at: string;
};

export type CreateTipPreferenceResponse = {
    tip_id: string;
    init_point: string;
    external_reference: string;
};

// ---------------------------------------------------------------------------
// Menu Layout Blocks — template-driven carta structure
// ---------------------------------------------------------------------------

export type BlockLayout = 'stack' | 'grid';
export type LayoutTemplate = 'drinks_first' | 'food_first' | 'custom';

/** A category entry inside a block (admin view) */
export type LayoutBlockCategory = {
    category_id: string;
    category_name: string;
    is_active: boolean;
    position: number;
};

/** Admin read/write model for a single layout block */
export type MenuLayoutBlock = {
    id: string;
    title: string;
    position: number;
    layout: BlockLayout;
    columns_desktop: number;
    columns_tablet: number;
    columns_mobile: number;
    badge_text: string;
    block_categories: LayoutBlockCategory[];
};

export type MenuLayoutBlockPayload = Omit<MenuLayoutBlock, 'id' | 'block_categories'> & {
    category_ids?: string[];
};

/** Public version — categories already include items */
export type PublicLayoutBlockCategory = {
    id: string;
    name: string;
    description: string;
    items: PublicMenuItem[];
};

export type PublicMenuLayoutBlock = {
    id: string;
    title: string;
    position: number;
    layout: BlockLayout;
    columns_desktop: number;
    columns_tablet: number;
    columns_mobile: number;
    badge_text: string;
    categories: PublicLayoutBlockCategory[];
};

