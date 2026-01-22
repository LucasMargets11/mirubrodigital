import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { fetchInvoice, fetchInvoices, fetchInvoiceSeries, issueInvoice } from './api';
import type { InvoiceFilters, IssueInvoicePayload } from './types';

const invoicesBaseKey = ['gestion', 'invoices'];
const invoiceSeriesKey = ['gestion', 'invoice-series'];

export function useInvoices(filters: InvoiceFilters) {
    return useQuery({
        queryKey: [...invoicesBaseKey, filters],
        queryFn: () => fetchInvoices(filters),
    });
}

export function useInvoice(invoiceId?: string) {
    return useQuery({
        queryKey: [...invoicesBaseKey, invoiceId],
        queryFn: () => fetchInvoice(invoiceId as string),
        enabled: Boolean(invoiceId),
    });
}

export function useInvoiceSeries() {
    return useQuery({
        queryKey: invoiceSeriesKey,
        queryFn: () => fetchInvoiceSeries(),
    });
}

export function useIssueInvoice() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (payload: IssueInvoicePayload) => issueInvoice(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: invoicesBaseKey });
            queryClient.invalidateQueries({ queryKey: ['gestion', 'sales'] });
        },
    });
}
