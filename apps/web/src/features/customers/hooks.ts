import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { createCustomer, listCustomers, updateCustomer } from './api';
import type { CustomerFilters, CustomerPayload } from './types';

const customersBaseKey = ['gestion', 'customers'];

export function useCustomers(filters: CustomerFilters, options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: [...customersBaseKey, filters],
        queryFn: () => listCustomers(filters),
        enabled: options?.enabled ?? true,
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
