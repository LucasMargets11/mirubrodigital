import type { CustomerSummary } from '@/features/customers/types';

export type Product = {
    id: string;
    name: string;
    sku: string | null;
    barcode: string | null;
    cost?: string;
    price: string;
    stock_min: string;
    stock_quantity?: string | null;
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
    cash_session_id?: string | null;
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
    cash_session_id?: string | null;
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

export type InventorySummaryStats = {
    total_products: number;
    low_stock: number;
    out_of_stock: number;
    healthy_products: number;
    healthy_ratio: number | null;
    low_ratio: number | null;
    out_ratio: number | null;
};

export type SalesTodaySummary = {
    total_amount: string;
    orders_count: number;
    average_ticket: string;
};

export type SaleTimelineItem = {
    id: string;
    number: number;
    status: SaleStatus;
    payment_method: PaymentMethod;
    total: string;
    created_at: string;
    customer_name: string | null;
};

export type TopProductMetric = {
    product_id: string | null;
    name: string;
    total_qty: string;
    total_sales: string;
};

export type CommercialSettings = {
    allow_sell_without_stock: boolean;
    block_sales_if_no_open_cash_session: boolean;
    require_customer_for_sales: boolean;
    allow_negative_price_or_discount: boolean;
    warn_on_low_stock_threshold_enabled: boolean;
    low_stock_threshold_default: number;
    enable_sales_notes: boolean;
    enable_receipts: boolean;
};
