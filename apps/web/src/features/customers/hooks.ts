import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { createCustomer, getCustomer, getCustomerQuotes, getCustomerSales, listCustomers, updateCustomer } from './api';
import type { CustomerFilters, CustomerPayload } from './types';

const customersBaseKey = ['gestion', 'customers'];

export function useCustomers(filters: CustomerFilters, options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: [...customersBaseKey, filters],
        queryFn: () => listCustomers(filters),
        enabled: options?.enabled ?? true,
    });
}

export function useCustomer(id: string) {
    return useQuery({
        queryKey: [...customersBaseKey, id],
        queryFn: () => getCustomer(id),
        enabled: !!id,
    });
}

export function useCustomerSales(customerId: string, params: { limit?: number; offset?: number } = {}, options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: [...customersBaseKey, customerId, 'sales', params],
        queryFn: () => getCustomerSales(customerId, params),
        enabled: (options?.enabled ?? true) && !!customerId,
    });
}

export function useCustomerQuotes(customerId: string, params: { limit?: number; offset?: number } = {}, options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: [...customersBaseKey, customerId, 'quotes', params],
        queryFn: () => getCustomerQuotes(customerId, params),
        enabled: (options?.enabled ?? true) && !!customerId,
    });
}

export function useCreateCustomer() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: CustomerPayload) => createCustomer(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: customersBaseKey });
        },
    });
}

export function useUpdateCustomer() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ id, payload }: { id: string; payload: Partial<CustomerPayload> }) => updateCustomer(id, payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: customersBaseKey });
        },
    });
}
