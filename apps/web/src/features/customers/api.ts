import { apiGet, apiPatch, apiPost } from '@/lib/api/client';
import type { PaginatedResponse } from '@/types/api';

import type { Customer, CustomerFilters, CustomerPayload } from './types';

function buildCustomerQuery(params: CustomerFilters) {
    const searchParams = new URLSearchParams();
    if (params.search) {
        searchParams.set('search', params.search);
    }
    if (params.includeInactive) {
        searchParams.set('include_inactive', 'true');
    }
    if (typeof params.limit === 'number') {
        searchParams.set('limit', String(params.limit));
    }
    if (typeof params.offset === 'number') {
        searchParams.set('offset', String(params.offset));
    }
    const query = searchParams.toString();
    return query ? `?${query}` : '';
}

export function listCustomers(filters: CustomerFilters = {}) {
    const query = buildCustomerQuery(filters);
    return apiGet<PaginatedResponse<Customer>>(`/api/v1/customers/${query}`);
}

export function createCustomer(payload: CustomerPayload) {
    return apiPost<Customer>('/api/v1/customers/', payload);
}

export function updateCustomer(id: string, payload: Partial<CustomerPayload>) {
    return apiPatch<Customer>(`/api/v1/customers/${id}/`, payload);
}

export function getCustomer(id: string) {
    return apiGet<Customer>(`/api/v1/customers/${id}/`);
}
