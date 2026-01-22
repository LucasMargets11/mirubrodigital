export type OrderStatus = 'pending' | 'preparing' | 'ready' | 'delivered' | 'canceled';
export type OrderChannel = 'dine_in' | 'pickup' | 'delivery';

export type OrderItem = {
    id: string;
    name: string;
    note: string;
    quantity: string;
    unit_price: string;
    total_price: string;
    product_id: string | null;
};

export type Order = {
    id: string;
    number: number;
    status: OrderStatus;
    status_label: string;
    channel: OrderChannel;
    channel_label: string;
    table_name: string;
    customer_name: string;
    note: string;
    total_amount: string;
    opened_at: string;
    updated_at: string;
    closed_at: string | null;
    items: OrderItem[];
};

export type OrderItemPayload = {
    name: string;
    quantity: number;
    unit_price: number;
    note?: string;
    product_id?: string;
};

export type OrderPayload = {
    channel: OrderChannel;
    table_name?: string;
    customer_name?: string;
    note?: string;
    items: OrderItemPayload[];
};
