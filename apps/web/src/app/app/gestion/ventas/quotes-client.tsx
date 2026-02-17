"use client";

import Link from 'next/link';
import { useState } from 'react';

import { useQuotes, useMarkQuoteSent } from '@/features/gestion/hooks';
import type { QuotesFilters, QuoteStatus } from '@/features/gestion/types';
import { getQuotePdfUrl } from '@/features/gestion/api';
import { formatCurrencySmart } from '@/lib/format';

const statusStyles: Record<QuoteStatus, string> = {
    draft: 'bg-slate-100 text-slate-700',
    sent: 'bg-blue-100 text-blue-700',
    accepted: 'bg-emerald-100 text-emerald-700',
    rejected: 'bg-rose-100 text-rose-700',
    expired: 'bg-amber-100 text-amber-700',
    converted: 'bg-violet-100 text-violet-700',
};

type QuotesClientProps = {
    canCreate: boolean;
    canSend: boolean;
};

export function QuotesClient({ canCreate, canSend }: QuotesClientProps) {
    const [filters, setFilters] = useState<QuotesFilters>({
        search: '',
        status: '',
        date_from: '',
        date_to: '',
        ordering: '-created_at',
    });

    const quotesQuery = useQuotes(filters);
    const quotes = quotesQuery.data?.results ?? [];
    const totalCount = quotesQuery.data?.count ?? 0;

    const markSentMutation = useMarkQuoteSent();

    const handleFilterChange = (key: keyof QuotesFilters, value: string) => {
        setFilters((prev) => ({
            ...prev,
            [key]: value,
        }));
    };

    const handleSort = (field: string) => {
        const currentOrdering = filters.ordering ?? '';
        const isDescending = currentOrdering.startsWith('-');
        const currentField = isDescending ? currentOrdering.slice(1) : currentOrdering;

        if (currentField === field) {
            setFilters((prev) => ({
                ...prev,
                ordering: isDescending ? field : `-${field}`,
            }));
        } else {
            setFilters((prev) => ({
                ...prev,
                ordering: `-${field}`,
            }));
        }
    };

    const getSortIcon = (field: string) => {
        const currentOrdering = filters.ordering ?? '';
        const isDescending = currentOrdering.startsWith('-');
        const currentField = isDescending ? currentOrdering.slice(1) : currentOrdering;

        if (currentField !== field) return '↕';
        return isDescending ? '↓' : '↑';
    };

    const handleMarkSent = async (quoteId: string) => {
        try {
            await markSentMutation.mutateAsync(quoteId);
        } catch (error) {
            console.error('Error marking quote as sent:', error);
        }
    };

    const handleDownloadPdf = (quoteId: string, quoteNumber: string) => {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const url = `${apiUrl}${getQuotePdfUrl(quoteId)}`;
        const link = document.createElement('a');
        link.href = url;
        link.download = `Presupuesto_${quoteNumber}.pdf`;
        link.target = '_blank';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    return (
        <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
            {quotesQuery.isError ? (
                <p className="mb-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
                    No pudimos cargar los presupuestos. Intentá de nuevo en unos segundos.
                </p>
            ) : null}
            <div className="grid gap-3 md:grid-cols-4">
                <input
                    type="search"
                    value={filters.search ?? ''}
                    onChange={(event) => handleFilterChange('search', event.target.value)}
                    placeholder="Buscar por número o cliente"
                    className="rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none md:col-span-2"
                />
                <select
                    value={filters.status ?? ''}
                    onChange={(event) => handleFilterChange('status', event.target.value)}
                    className="rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
                >
                    <option value="">Todos los estados</option>
                    <option value="draft">Borrador</option>
                    <option value="sent">Enviado</option>
                    <option value="accepted">Aceptado</option>
                    <option value="rejected">Rechazado</option>
                    <option value="expired">Vencido</option>
                    <option value="converted">Convertido</option>
                </select>
                <input
                    type="date"
                    value={filters.date_from ?? ''}
                    onChange={(event) => handleFilterChange('date_from', event.target.value)}
                    placeholder="Desde"
                    className="rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
                />
            </div>
            <p className="mt-3 text-xs uppercase tracking-wide text-slate-400">{totalCount} registros</p>
            <div className="mt-4 overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-100 text-sm">
                    <thead>
                        <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                            <th 
                                className="cursor-pointer px-3 py-2 hover:text-slate-700"
                                onClick={() => handleSort('number')}
                            >
                                Número {getSortIcon('number')}
                            </th>
                            <th className="px-3 py-2">Cliente</th>
                            <th 
                                className="cursor-pointer px-3 py-2 hover:text-slate-700"
                                onClick={() => handleSort('created_at')}
                            >
                                Fecha {getSortIcon('created_at')}
                            </th>
                            <th 
                                className="cursor-pointer px-3 py-2 hover:text-slate-700"
                                onClick={() => handleSort('valid_until')}
                            >
                                Vence {getSortIcon('valid_until')}
                            </th>
                            <th 
                                className="cursor-pointer px-3 py-2 text-right hover:text-slate-700"
                                onClick={() => handleSort('total')}
                            >
                                Total {getSortIcon('total')}
                            </th>
                            <th 
                                className="cursor-pointer px-3 py-2 hover:text-slate-700"
                                onClick={() => handleSort('status')}
                            >
                                Estado {getSortIcon('status')}
                            </th>
                            <th className="px-3 py-2" />
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                        {quotesQuery.isLoading && (
                            <tr>
                                <td colSpan={7} className="px-3 py-6 text-center text-slate-500">
                                    Cargando presupuestos...
                                </td>
                            </tr>
                        )}
                        {!quotesQuery.isLoading && quotes.length === 0 && (
                            <tr>
                                <td colSpan={7} className="px-3 py-6 text-center text-slate-500">
                                    Aún no creaste presupuestos.
                                </td>
                            </tr>
                        )}
                        {quotes.map((quote) => (
                            <tr key={quote.id} className="hover:bg-slate-50">
                                <td className="px-3 py-3">
                                    <span className="font-semibold text-slate-900">{quote.number}</span>
                                </td>
                                <td className="px-3 py-3">
                                    <p className="font-medium text-slate-900">
                                        {quote.customer?.name || quote.customer_name || 'Sin cliente'}
                                    </p>
                                    {(quote.customer_email || quote.customer_phone) ? (
                                        <p className="text-xs text-slate-400">
                                            {quote.customer_email || quote.customer_phone}
                                        </p>
                                    ) : null}
                                </td>
                                <td className="px-3 py-3 text-slate-500">
                                    {new Date(quote.created_at).toLocaleDateString('es-AR', {
                                        dateStyle: 'medium',
                                    })}
                                </td>
                                <td className="px-3 py-3 text-slate-500">
                                    {quote.valid_until 
                                        ? new Date(quote.valid_until).toLocaleDateString('es-AR', {
                                            dateStyle: 'medium',
                                          })
                                        : '—'}
                                </td>
                                <td className="px-3 py-3 text-right font-semibold text-slate-900">
                                    {formatCurrencySmart(quote.total)}
                                </td>
                                <td className="px-3 py-3">
                                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${statusStyles[quote.status]}`}>
                                        {quote.status_label}
                                    </span>
                                </td>
                                <td className="px-3 py-3">
                                    <div className="flex items-center gap-2">
                                        <button
                                            onClick={() => handleDownloadPdf(quote.id, quote.number)}
                                            className="text-sm font-medium text-blue-600 hover:text-blue-800"
                                            title="Descargar PDF"
                                        >
                                            PDF
                                        </button>
                                        {canSend && quote.status === 'draft' && (
                                            <button
                                                onClick={() => handleMarkSent(quote.id)}
                                                disabled={markSentMutation.isPending}
                                                className="text-sm font-medium text-emerald-600 hover:text-emerald-800 disabled:opacity-50"
                                            >
                                                Enviar
                                            </button>
                                        )}
                                        <Link
                                            href={`/app/gestion/ventas/presupuestos/${quote.id}` as any}
                                            className="text-sm font-semibold text-slate-600 hover:text-slate-900"
                                        >
                                            Ver →
                                        </Link>
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
