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

// ─── PDF Download ────────────────────────────────────────────────────────────

export type PdfDownloadError =
    | { type: 'issuer_profile_incomplete'; missing_fields: string[] }
    | { type: 'generic'; message: string };

/**
 * Descarga los bytes del PDF de una factura.
 * Lanza objetos tipados de PdfDownloadError para errores conocidos (422, etc.)
 * de modo que los componentes puedan mostrar mensajes amigables.
 */
export async function downloadInvoicePdf(invoiceId: string): Promise<Blob> {
    const response = await fetch(buildInvoicePdfUrl(invoiceId), {
        credentials: 'include',
    });

    if (response.ok) {
        return response.blob();
    }

    // Intentar leer JSON de la respuesta de error
    const data = await response.json().catch(() => ({}));

    if (response.status === 422 && data.code === 'issuer_profile_incomplete') {
        // eslint-disable-next-line @typescript-eslint/no-throw-literal
        throw {
            type: 'issuer_profile_incomplete',
            missing_fields: (data.missing_fields as string[]) ?? [],
        } satisfies PdfDownloadError;
    }

    // eslint-disable-next-line @typescript-eslint/no-throw-literal
    throw {
        type: 'generic',
        message: (data.message as string) ?? 'No se pudo descargar el PDF. Intentá nuevamente.',
    } satisfies PdfDownloadError;
}
