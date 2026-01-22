import type { CustomerSummary } from '@/features/customers/types';

export type Product = {
    id: string;
    name: string;
    sku: string | null;
    barcode: string | null;
    cost?: string;
    price: string;
    stock_min: string;
    is_active: boolean;
    created_at: string;
    updated_at: string;
};

export type ProductSummary = {
    id: string;
    name: string;
    sku: string | null;
    barcode: string | null;
    stock_min: string;
    is_active: boolean;
};

export type ProductStock = {
    id: number;
    product: ProductSummary;
    quantity: string;
    status: 'ok' | 'low' | 'out';
    updated_at: string;
};

export type StockMovement = {
    id: string;
    product: ProductSummary;
    movement_type: 'IN' | 'OUT' | 'ADJUST' | 'WASTE';
    quantity: string;
    note: string;
    created_at: string;
};

export type ProductPayload = {
    name: string;
    sku?: string;
    barcode?: string;
    cost: number;
    price: number;
    stock_min: number;
    is_active?: boolean;
};

export type StockMovementPayload = {
    product_id: string;
    movement_type: StockMovement['movement_type'];
    quantity: number;
    note?: string;
};

export type SaleStatus = 'completed' | 'cancelled';
export type PaymentMethod = 'cash' | 'transfer' | 'card' | 'other';

export type SaleItem = {
    id: string;
    product_id?: string | null;
    product_name: string;
    quantity: string;
    unit_price: string;
    line_total: string;
};

export type SaleInvoiceSummary = {
    id: string;
    full_number: string;
    status: 'issued' | 'voided';
};

export type SalePayment = {
    id: string;
    method: 'cash' | 'debit' | 'credit' | 'transfer' | 'wallet' | 'account';
    method_label?: string;
    amount: string;
    reference: string;
    created_at: string;
};

export type Sale = {
    id: string;
    number: number;
    status: SaleStatus;
    status_label: string;
    payment_method: PaymentMethod;
    payment_method_label: string;
    customer_id: string | null;
    customer_name: string | null;
    customer?: CustomerSummary | null;
    subtotal: string;
    discount: string;
    total: string;
    notes: string;
    created_at: string;
    items_count?: number;
    items?: SaleItem[];
    invoice?: SaleInvoiceSummary | null;
    paid_total?: string;
    balance?: string;
    payments?: SalePayment[];
};

export type SalesFilters = {
    search?: string;
    status?: string;
    payment_method?: string;
    date_from?: string;
    date_to?: string;
};

export type SaleItemPayload = {
    product_id: string;
    quantity: number;
    unit_price?: number;
};

export type SalePayload = {
    customer_id?: string | null;
    payment_method: PaymentMethod;
    discount?: number;
    notes?: string;
    items: SaleItemPayload[];
};

export type InventoryValuationItem = {
    product_id: string;
    name: string;
    sku: string | null;
    is_active: boolean;
    qty: string;
    price: string;
    sale_value: string;
    stock_min: string;
    status: 'ok' | 'low' | 'out';
    cost?: string;
    cost_value?: string;
    potential_profit?: string;
    margin_pct?: string;
};

export type InventoryValuationTotals = {
    total_cost_value: string | null;
    total_sale_value: string;
    total_potential_profit: string | null;
    items_count: number;
};

export type InventoryValuationResponse = {
    totals: InventoryValuationTotals;
    items: InventoryValuationItem[];
};

export type InventoryValuationFilters = {
    search?: string;
    status?: string;
    sort?: 'profit_desc' | 'sale_value_desc' | 'qty_desc' | 'name_asc';
    onlyInStock?: boolean;
    active?: 'true' | 'false' | 'all';
};
