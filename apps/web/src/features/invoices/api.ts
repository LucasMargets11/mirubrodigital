import { apiGet, apiPost } from '@/lib/api/client';

import type { Invoice, InvoiceFilters, InvoiceListItem, InvoiceSeries, IssueInvoicePayload } from './types';

const API_BASE = '/api/v1/invoices';

function buildQuery(params: Record<string, string | undefined>) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== '') {
            searchParams.append(key, value);
        }
    });
    const serialized = searchParams.toString();
    return serialized ? `?${serialized}` : '';
}

export function fetchInvoices(filters: InvoiceFilters = {}) {
    const query = buildQuery({
        q: filters.q,
        status: filters.status,
        date_from: filters.date_from,
        date_to: filters.date_to,
    });
    return apiGet<InvoiceListItem[]>(`${API_BASE}/${query}`);
}

export function fetchInvoice(invoiceId: string) {
    return apiGet<Invoice>(`${API_BASE}/${invoiceId}/`);
}

export function fetchInvoiceSeries() {
    return apiGet<InvoiceSeries[]>(`${API_BASE}/series/`);
}

export function issueInvoice(payload: IssueInvoicePayload) {
    return apiPost<Invoice>(`${API_BASE}/issue/`, payload);
}

const PUBLIC_API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export function buildInvoicePdfUrl(invoiceId: string) {
    return `${PUBLIC_API_URL}${API_BASE}/${invoiceId}/pdf/`;
}
