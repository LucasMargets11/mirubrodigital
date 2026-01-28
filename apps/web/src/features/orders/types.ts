import type { CashPaymentMethod, CashSession } from '@/features/cash/types';
import type { Sale } from '@/features/gestion/types';

export type OrderStatus = 'draft' | 'open' | 'sent' | 'paid' | 'cancelled';
export type OrderChannel = 'dine_in' | 'pickup' | 'delivery';

export type OrderItem = {
    id: string;
    name: string;
    note: string;
    quantity: string;
    unit_price: string;
    total_price: string;
    product_id: string | null;
    modifiers: unknown[];
    sold_without_stock: boolean;
};

export type Order = {
    id: string;
    number: number;
    status: OrderStatus;
    status_label: string;
    channel: OrderChannel;
    channel_label: string;
    table_id: string | null;
    table_code: string | null;
    table_name: string;
    customer_name: string;
    note: string;
    total_amount: string;
    subtotal_amount: string;
    opened_at: string;
    updated_at: string;
    closed_at: string | null;
    items: OrderItem[];
    sale_id: string | null;
    sale_number: number | null;
    sale_total: string | null;
};

export type OrderItemPayload = {
    name: string;
    quantity: number;
    unit_price: number;
    note?: string;
    product_id?: string;
    modifiers?: unknown[];
};

export type OrderPayload = {
    channel: OrderChannel;
    table_id?: string | null;
    customer_name?: string;
    note?: string;
    items: OrderItemPayload[];
};

export type OrderStartPayload = {
    table_id: string;
    order_id?: string | null;
    channel?: OrderChannel;
    customer_name?: string;
    note?: string;
};

export type OrderItemCreatePayload = {
    name?: string;
    note?: string;
    quantity: number;
    unit_price?: number;
    product_id?: string | null;
    modifiers?: unknown[];
};

export type OrderItemUpdatePayload = {
    name?: string;
    note?: string | null;
    quantity?: number;
    unit_price?: number;
    product_id?: string | null;
    modifiers?: unknown[];
};

export type OrderUpdatePayload = {
    channel?: OrderChannel;
    table_id?: string | null;
    table_name?: string | null;
    customer_name?: string | null;
    note?: string | null;
};

export type CloseOrderPayload = {
    payment_method: string;
    discount?: number;
    notes?: string;
    customer_id?: string;
    cash_session_id?: string;
};

export type CheckoutPaymentOption = {
    value: CashPaymentMethod | string;
    label: string;
};

export type OrderCheckoutTotals = {
    order_total: string;
    sale_total: string;
    paid_total: string;
    balance: string;
};

export type OrderCheckoutResponse = {
    order: Order;
    sale: Sale | null;
    totals: OrderCheckoutTotals;
    payment_methods: CheckoutPaymentOption[];
    cash_session: CashSession | null;
    allow_partial_payments: boolean;
    default_payment_method: string;
};

export type CreateSalePayload = {
    payment_method?: string;
    discount?: number;
    notes?: string;
    customer_id?: string | null;
};

export type CheckoutPaymentInput = {
    method: CashPaymentMethod;
    amount: number;
    reference?: string;
};

export type PayOrderPayload = {
    payments: CheckoutPaymentInput[];
    cash_session_id?: string | null;
};
