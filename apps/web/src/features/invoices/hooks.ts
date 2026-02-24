import { useCallback, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { downloadInvoicePdf, fetchInvoice, fetchInvoices, fetchInvoiceSeries, issueInvoice } from './api';
import type { InvoiceFilters, IssueInvoicePayload } from './types';
import type { PdfDownloadError } from './api';

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

/**
 * Hook para descargar el PDF de una factura con manejo de errores tipado.
 *
 * Si el backend responde 422 con código "issuer_profile_incomplete",
 * el error tendrá type === 'issuer_profile_incomplete' y la lista de campos faltantes.
 * En caso de éxito, abre el PDF en una nueva pestaña a partir del blob descargado.
 */
export function useDownloadInvoicePdf() {
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<PdfDownloadError | null>(null);

    const download = useCallback(async (invoiceId: string) => {
        setIsLoading(true);
        setError(null);
        try {
            const blob = await downloadInvoicePdf(invoiceId);
            const objectUrl = URL.createObjectURL(blob);
            window.open(objectUrl, '_blank', 'noreferrer');
            // Revocar después de un tiempo prudencial para que el navegador complete la apertura
            setTimeout(() => URL.revokeObjectURL(objectUrl), 10_000);
        } catch (err) {
            setError(err as PdfDownloadError);
        } finally {
            setIsLoading(false);
        }
    }, []);

    const clearError = useCallback(() => setError(null), []);

    return { download, isLoading, error, clearError };
}
