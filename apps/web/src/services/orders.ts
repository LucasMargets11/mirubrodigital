import { api } from '@/lib/api';

export interface OrderItem {
    id: string;
    product: string;
    product_name: string;
    product_sku: string;
    quantity: number;
    unit_price: number;
    discount: number;
    subtotal: number;
    reserved_quantity: number;
    delivered_quantity: number;
}

export interface OrderPayment {
    id: string;
    amount: number;
    payment_date: string;
    payment_method: string;
    notes: string;
}

export interface OrderHistory {
    id: string;
    action: string;
    user_name: string;
    created_at: string;
}

export interface Order {
    id: string;
    number: string;
    customer: string; // ID
    customer_name: string;
    status: 'draft' | 'pending_confirmation' | 'confirmed' | 'in_preparation' | 'ready_for_delivery' | 'delivered' | 'cancelled';
    status_display: string;
    payment_status: 'pending' | 'partial' | 'paid';
    payment_status_display: string;
    total: number;
    total_paid: number;
    pending_balance: number;
    order_date: string;
    estimated_delivery_date?: string;
    items_count?: number;
    created_at: string;
    
    // Detail only
    items?: OrderItem[];
    payments?: OrderPayment[];
    history?: OrderHistory[];
    notes?: string;
}

export interface OrderFilters {
    status?: string;
    customer_name?: string;
    from_date?: string;
    to_date?: string;
    page?: number;
    limit?: number;
}

export const ordersService = {
    list: async (filters: OrderFilters = {}) => {
        const query = new URLSearchParams();
        if (filters.status) query.append('status', filters.status);
        if (filters.customer_name) query.append('search', filters.customer_name);
        // ... more filters
        const response = await api.get(`/sales/orders/?${query.toString()}`);
        return response.data;
    },
    
    get: async (id: string) => {
        const response = await api.get(`/sales/orders/${id}/`);
        return response.data;
    },
    
    create: async (payload: any) => {
        const response = await api.post('/sales/orders/', payload);
        return response.data;
    },
    
    update: async (id: string, payload: any) => {
        const response = await api.patch(`/sales/orders/${id}/`, payload);
        return response.data;
    },
    
    confirm: async (id: string) => {
        const response = await api.post(`/sales/orders/${id}/confirm/`);
        return response.data;
    },
    
    cancel: async (id: string) => {
        const response = await api.post(`/sales/orders/${id}/cancel/`);
        return response.data;
    },
    
    markInPreparation: async (id: string) => {
        const response = await api.post(`/sales/orders/${id}/mark_in_preparation/`);
        return response.data;
    },

    markReady: async (id: string) => {
        const response = await api.post(`/sales/orders/${id}/mark_ready/`);
        return response.data;
    },
    
    deliver: async (id: string) => {
        const response = await api.post(`/sales/orders/${id}/deliver/`);
        return response.data;
    },
    
    registerPayment: async (id: string, payload: { amount: number, method: string, notes?: string }) => {
        const response = await api.post(`/sales/orders/${id}/collect_payment/`, payload);
        return response.data;
    }
};
