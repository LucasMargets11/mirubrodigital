"use client";

import Link from 'next/link';
import { useMemo, useState } from 'react';

import { buildInvoicePdfUrl } from '@/features/invoices/api';
import { useInvoices } from '@/features/invoices/hooks';
import type { InvoiceFilters } from '@/features/invoices/types';

const statusLabels: Record<string, string> = {
    issued: 'Emitida',
    voided: 'Anulada',
};

const statusStyles: Record<string, string> = {
    issued: 'bg-emerald-100 text-emerald-700',
    voided: 'bg-rose-100 text-rose-700',
};

function formatCurrency(value: string | number) {
    const numeric = typeof value === 'number' ? value : Number(value);
    return new Intl.NumberFormat('es-AR', {
        style: 'currency',
        currency: 'ARS',
        maximumFractionDigits: 2,
    }).format(Number.isNaN(numeric) ? 0 : numeric);
}

function formatDate(value: string) {
    return new Date(value).toLocaleString('es-AR', { dateStyle: 'medium', timeStyle: 'short' });
}

type InvoicesClientProps = {
    canIssue: boolean;
};

export function InvoicesClient({ canIssue }: InvoicesClientProps) {
    const [filters, setFilters] = useState<InvoiceFilters>({ q: '', status: '', date_from: '', date_to: '' });
    const invoicesQuery = useInvoices(filters);
    const invoices = invoicesQuery.data ?? [];

    const totalIssued = useMemo(() => invoices.reduce((sum, invoice) => sum + Number(invoice.total || 0), 0), [invoices]);

    const updateFilter = <K extends keyof InvoiceFilters>(key: K, value: InvoiceFilters[K]) => {
        setFilters((prev) => ({
            ...prev,
            [key]: value,
        }));
    };

    return (
        <section className="space-y-5">
            <header className="flex flex-col gap-3 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm md:flex-row md:items-center md:justify-between">
                <div>
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Documentos</p>
                    <h1 className="text-2xl font-semibold text-slate-900">Facturas internas</h1>
                    <p className="text-sm text-slate-500">Comprobantes digitales listos para compartir con tus clientes.</p>
                </div>
                {canIssue ? (
                    <div className="text-sm text-slate-500">
                        Emití desde una venta: abrí la venta y tocá “Generar factura”.
                    </div>
                ) : null}
            </header>
            <div className="grid gap-4 md:grid-cols-3">
                <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                    <p className="text-xs uppercase tracking-wide text-slate-400">Facturas del período</p>
                    <p className="mt-2 text-3xl font-semibold text-slate-900">{invoices.length}</p>
                </article>
                <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                    <p className="text-xs uppercase tracking-wide text-slate-400">Importe emitido</p>
                    <p className="mt-2 text-3xl font-semibold text-slate-900">{formatCurrency(totalIssued)}</p>
                </article>
                <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                    <p className="text-xs uppercase tracking-wide text-slate-400">Estado</p>
                    <p className="mt-2 text-3xl font-semibold text-slate-900">Digital</p>
                    <p className="text-xs text-slate-500">Comprobante no fiscal</p>
                </article>
            </div>
            <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                {invoicesQuery.isError ? (
                    <p className="mb-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
                        No pudimos cargar las facturas. Intentá nuevamente.
                    </p>
                ) : null}
                <div className="grid gap-3 md:grid-cols-4">
                    <input
                        type="search"
                        value={filters.q ?? ''}
                        onChange={(event) => updateFilter('q', event.target.value)}
                        placeholder="Buscar número o cliente"
                        className="rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none md:col-span-2"
                    />
                    <select
                        value={filters.status ?? ''}
                        onChange={(event) => updateFilter('status', event.target.value as InvoiceFilters['status'])}
                        className="rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
                    >
                        <option value="">Todos los estados</option>
                        <option value="issued">Emitidas</option>
                        <option value="voided">Anuladas</option>
                    </select>
                    <input
                        type="date"
                        value={filters.date_from ?? ''}
                        onChange={(event) => updateFilter('date_from', event.target.value)}
                        className="rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
                    />
                    <input
                        type="date"
                        value={filters.date_to ?? ''}
                        onChange={(event) => updateFilter('date_to', event.target.value)}
                        className="rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
                    />
                </div>
                <p className="mt-3 text-xs uppercase tracking-wide text-slate-400">{invoices.length} resultados</p>
                <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-100 text-sm">
                        <thead>
                            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                                <th className="px-3 py-2">Factura</th>
                                <th className="px-3 py-2">Fecha</th>
                                <th className="px-3 py-2">Venta</th>
                                <th className="px-3 py-2">Cliente</th>
                                <th className="px-3 py-2 text-right">Total</th>
                                <th className="px-3 py-2" />
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {invoicesQuery.isLoading && (
                                <tr>
                                    <td colSpan={6} className="px-3 py-6 text-center text-slate-500">
                                        Cargando facturas...
                                    </td>
                                </tr>
                            )}
                            {!invoicesQuery.isLoading && invoices.length === 0 && (
                                <tr>
                                    <td colSpan={6} className="px-3 py-6 text-center text-slate-500">
                                        Aún no generaste facturas. Entrá a una venta y emití tu primer comprobante.
                                    </td>
                                </tr>
                            )}
                            {invoices.map((invoice) => (
                                <tr key={invoice.id} className="hover:bg-slate-50">
                                    <td className="px-3 py-3">
                                        <div className="flex items-center gap-2">
                                            <span className="font-semibold text-slate-900">{invoice.full_number}</span>
                                            <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${statusStyles[invoice.status] ?? 'bg-slate-100 text-slate-600'}`}>
                                                {statusLabels[invoice.status] ?? invoice.status}
                                            </span>
                                        </div>
                                    </td>
                                    <td className="px-3 py-3 text-slate-500">{formatDate(invoice.issued_at)}</td>
                                    <td className="px-3 py-3 text-slate-500">Venta #{invoice.sale_number}</td>
                                    <td className="px-3 py-3">
                                        <p className="font-medium text-slate-900">{invoice.customer_name || 'Consumidor final'}</p>
                                    </td>
                                    <td className="px-3 py-3 text-right font-semibold text-slate-900">{formatCurrency(invoice.total)}</td>
                                    <td className="px-3 py-3 text-right">
                                        <div className="flex items-center justify-end gap-3 text-sm font-semibold">
                                            <Link href={`/app/gestion/facturas/${invoice.id}`} className="text-slate-600 hover:text-slate-900">
                                                Ver detalle →
                                            </Link>
                                            <a
                                                href={buildInvoicePdfUrl(invoice.id)}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="text-slate-600 hover:text-slate-900"
                                            >
                                                PDF
                                            </a>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </section>
    );
}
