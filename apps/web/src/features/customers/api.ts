import { apiDelete, apiGet, apiPatch, apiPost } from '@/lib/api/client';
import type { PaginatedResponse } from '@/types/api';

import type {
    Customer,
    CustomerAppointmentHistoryItem,
    CustomerAppointmentsScope,
    CustomerContactPreferences,
    CustomerContactPreferencesPayload,
    CustomerDelivery,
    CustomerDetail,
    CustomerFilters,
    CustomerNote,
    CustomerPayload,
    CustomerReminder,
    CustomerReminderPayload,
    CustomerRemindersPage,
    CustomerRemindersScope,
    CustomerTimelinePage,
    CustomerTimelineType,
} from './types';

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
    return apiGet<CustomerDetail>(`/api/v1/customers/${id}/`);
}

export function getCustomerAppointments(
    customerId: string,
    params: { scope: CustomerAppointmentsScope; limit?: number; offset?: number },
) {
    const searchParams = new URLSearchParams({ scope: params.scope });
    if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
    if (params.offset !== undefined) searchParams.set('offset', String(params.offset));
    return apiGet<PaginatedResponse<CustomerAppointmentHistoryItem>>(
        `/api/v1/customers/${customerId}/appointments/?${searchParams.toString()}`,
    );
}

export function getCustomerTimeline(
    customerId: string,
    params: { types?: CustomerTimelineType[]; limit?: number; offset?: number } = {},
) {
    const searchParams = new URLSearchParams();
    if (params.types && params.types.length > 0) searchParams.set('types', params.types.join(','));
    if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
    if (params.offset !== undefined) searchParams.set('offset', String(params.offset));
    const query = searchParams.toString();
    return apiGet<CustomerTimelinePage>(`/api/v1/customers/${customerId}/timeline/${query ? `?${query}` : ''}`);
}

export function listCustomerNotes(customerId: string, params: { limit?: number; offset?: number } = {}) {
    const searchParams = new URLSearchParams();
    if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
    if (params.offset !== undefined) searchParams.set('offset', String(params.offset));
    const query = searchParams.toString();
    return apiGet<PaginatedResponse<CustomerNote>>(`/api/v1/customers/${customerId}/notes/${query ? `?${query}` : ''}`);
}

export function createCustomerNote(customerId: string, body: string) {
    return apiPost<CustomerNote>(`/api/v1/customers/${customerId}/notes/`, { body });
}

export function updateCustomerNote(customerId: string, noteId: string, body: string) {
    return apiPatch<CustomerNote>(`/api/v1/customers/${customerId}/notes/${noteId}/`, { body });
}

export function deleteCustomerNote(customerId: string, noteId: string) {
    return apiDelete<void>(`/api/v1/customers/${customerId}/notes/${noteId}/`);
}

// ── Recordatorios internos (CUSTOMER 07A) ────────────────────────────────────
// Sin DELETE: completar/cancelar = PATCH `status`.

export function listCustomerReminders(
    customerId: string,
    params: { scope?: CustomerRemindersScope; limit?: number; offset?: number } = {},
) {
    const searchParams = new URLSearchParams();
    if (params.scope) searchParams.set('scope', params.scope);
    if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
    if (params.offset !== undefined) searchParams.set('offset', String(params.offset));
    const query = searchParams.toString();
    return apiGet<CustomerRemindersPage>(`/api/v1/customers/${customerId}/reminders/${query ? `?${query}` : ''}`);
}

export function createCustomerReminder(customerId: string, payload: CustomerReminderPayload) {
    return apiPost<CustomerReminder>(`/api/v1/customers/${customerId}/reminders/`, payload);
}

export function updateCustomerReminder(
    customerId: string,
    reminderId: string,
    payload: Partial<CustomerReminderPayload> & { status?: 'completed' | 'cancelled' },
) {
    return apiPatch<CustomerReminder>(`/api/v1/customers/${customerId}/reminders/${reminderId}/`, payload);
}

// ── Preferencias de contacto (CUSTOMER 07D.1) ───────────────────────────────
// Un solo recurso para todos los canales (GET/PATCH).

export function getCustomerContactPreferences(customerId: string) {
    return apiGet<CustomerContactPreferences>(`/api/v1/customers/${customerId}/contact-preferences/`);
}

export function updateCustomerContactPreferences(customerId: string, payload: CustomerContactPreferencesPayload) {
    return apiPatch<CustomerContactPreferences>(`/api/v1/customers/${customerId}/contact-preferences/`, payload);
}

// ── Comunicaciones externas (CUSTOMER 07D.2): solo lectura ──────────────────

export function listCustomerDeliveries(customerId: string, params: { limit?: number; offset?: number } = {}) {
    const searchParams = new URLSearchParams();
    if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
    if (params.offset !== undefined) searchParams.set('offset', String(params.offset));
    const query = searchParams.toString();
    return apiGet<PaginatedResponse<CustomerDelivery>>(`/api/v1/customers/${customerId}/deliveries/${query ? `?${query}` : ''}`);
}
