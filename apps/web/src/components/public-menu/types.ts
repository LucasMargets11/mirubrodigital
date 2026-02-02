export interface MenuItem {
    id: number | string;
    name: string;
    description?: string;
    price: number | string;
    is_available: boolean;
    image?: string;
    is_featured?: boolean; // Assumed field
}

export interface MenuCategory {
    id: number | string;
    name: string;
    description?: string;
    items: MenuItem[];
}

export interface MenuConfig {
    brand_name: string;
    description?: string;
    theme_json?: {
        primary?: string;
        secondary?: string;
        background?: string;
        text?: string;
        font?: string;
    };
    address?: string;
    phone?: string;
}
