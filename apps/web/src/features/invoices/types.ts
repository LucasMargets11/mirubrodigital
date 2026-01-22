import type { SaleItem } from '@/features/gestion/types';

export type InvoiceStatus = 'issued' | 'voided';

export type InvoiceListItem = {
    id: string;
    full_number: string;
    status: InvoiceStatus;
    issued_at: string;
    sale_id: string;
    sale_number: number;
    customer_name: string | null;
    total: string;
    pdf_url: string;
};

export type Invoice = InvoiceListItem & {
    series_code: string;
    series_prefix?: string | null;
    number: number;
    subtotal: string;
    discount: string;
    customer_tax_id: string | null;
    customer_address: string | null;
    items: SaleItem[];
};

export type InvoiceFilters = {
    q?: string;
    status?: InvoiceStatus | '';
    date_from?: string;
    date_to?: string;
};

export type InvoiceSeries = {
    id: string;
    code: string;
    prefix?: string | null;
    next_number: number;
    is_active: boolean;
};

export type IssueInvoicePayload = {
    sale_id: string;
    series_code?: string;
    customer_name?: string;
    customer_tax_id?: string;
    customer_address?: string;
};
