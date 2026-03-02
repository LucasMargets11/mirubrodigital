"use client";

import Link from 'next/link';
import { useState } from 'react';

import { useCustomer, useCustomerQuotes, useCustomerSales } from '@/features/customers/hooks';
import { formatCurrencySmart } from '@/lib/format';
import type { QuoteStatus, SaleStatus } from '@/features/gestion/types';

const saleStatusStyles: Record<SaleStatus, string> = {
    completed: 'bg-emerald-100 text-emerald-700',
    cancelled: 'bg-rose-100 text-rose-700',
};

const quoteStatusStyles: Record<QuoteStatus, string> = {
    draft: 'bg-slate-100 text-slate-700',
    sent: 'bg-blue-100 text-blue-700',
    accepted: 'bg-emerald-100 text-emerald-700',
    rejected: 'bg-rose-100 text-rose-700',
    expired: 'bg-amber-100 text-amber-700',
    converted: 'bg-violet-100 text-violet-700',
};

function fmtDate(iso: string) {
    return new Date(iso).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

type Tab = 'sales' | 'quotes';

type CustomerDetailClientProps = {
    customerId: string;
    canManage: boolean;
    canViewSales: boolean;
    canViewQuotes: boolean;
};

export function CustomerDetailClient({ customerId, canManage, canViewSales, canViewQuotes }: CustomerDetailClientProps) {
    const [activeTab, setActiveTab] = useState<Tab>('sales');

    const customerQuery = useCustomer(customerId);
    const salesQuery = useCustomerSales(customerId, { limit: 25 }, { enabled: canViewSales });
    const quotesQuery = useCustomerQuotes(customerId, { limit: 25 }, { enabled: canViewQuotes && activeTab === 'quotes' });

    const customer = customerQuery.data;
    const sales = salesQuery.data?.results ?? [];
    const quotes = quotesQuery.data?.results ?? [];

    const tabs: Array<{ key: Tab; label: string; show: boolean }> = (
        [
            { key: 'sales' as const, label: 'Ventas', show: canViewSales },
            { key: 'quotes' as const, label: 'Presupuestos', show: canViewQuotes },
        ] satisfies Array<{ key: Tab; label: string; show: boolean }>
    ).filter((t) => t.show);

    if (customerQuery.isLoading) {
        return (
            <section className="space-y-4">
                <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                    <p className="text-sm text-slate-500">Cargando cliente...</p>
                </div>
            </section>
        );
    }

    if (!customer) {
        return (
            <section className="space-y-4">
                <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                    <p className="text-sm text-slate-500">Cliente no encontrado.</p>
                </div>
            </section>
        );
    }

    return (
        <section className="space-y-4">
            {/* Header */}
            <header className="flex flex-col gap-3 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm md:flex-row md:items-center md:justify-between">
                <div className="flex flex-col gap-1">
                    <Link
                        href={'/app/gestion/clientes' as any}
                        className="text-xs font-semibold uppercase tracking-wide text-slate-400 hover:text-slate-700"
                    >
                        ← Clientes
                    </Link>
                    <h2 className="text-2xl font-semibold text-slate-900">{customer.name}</h2>
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-500">
                        {customer.email ? <span>{customer.email}</span> : null}
                        {customer.phone ? <span>{customer.phone}</span> : null}
                        {customer.doc_number ? (
                            <span>
                                {customer.doc_type?.toUpperCase() ?? ''} {customer.doc_number}
                            </span>
                        ) : null}
                    </div>
                </div>
                {canManage ? (
                    <Link
                        href={`/app/gestion/clientes/${customerId}/editar` as any}
                        className="w-fit rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:border-slate-900 hover:text-slate-900"
                    >
                        Editar cliente
                    </Link>
                ) : null}
            </header>

            {/* Tabs */}
            {tabs.length > 0 ? (
                <div className="rounded-3xl border border-slate-200 bg-white shadow-sm">
                    {/* Tab navigation */}
                    <div className="flex gap-1 border-b border-slate-100 px-4 pt-3">
                        {tabs.map((tab) => (
                            <button
                                key={tab.key}
                                type="button"
                                onClick={() => setActiveTab(tab.key)}
                                className={`rounded-t-xl px-4 py-2 text-sm font-semibold transition-colors ${
                                    activeTab === tab.key
                                        ? 'bg-slate-900 text-white'
                                        : 'text-slate-600 hover:text-slate-900'
                                }`}
                            >
                                {tab.label}
                            </button>
                        ))}
                    </div>

                    {/* Tab content */}
                    <div className="p-4">
                        {activeTab === 'sales' && canViewSales ? (
                            <SalesTab
                                sales={sales}
                                isLoading={salesQuery.isLoading}
                                total={salesQuery.data?.count ?? 0}
                            />
                        ) : null}
                        {activeTab === 'quotes' && canViewQuotes ? (
                            <QuotesTab
                                quotes={quotes}
                                isLoading={quotesQuery.isLoading}
                                total={quotesQuery.data?.count ?? 0}
                            />
                        ) : null}
                    </div>
                </div>
            ) : null}
        </section>
    );
}

// ── Sales tab ─────────────────────────────────────────────────────────────────

type SalesTabProps = {
    sales: import('@/features/gestion/types').Sale[];
    isLoading: boolean;
    total: number;
};

function SalesTab({ sales, isLoading, total }: SalesTabProps) {
    return (
        <div className="overflow-x-auto">
            <p className="mb-3 text-xs uppercase tracking-wide text-slate-400">{total} ventas</p>
            <table className="min-w-full divide-y divide-slate-100 text-sm">
                <thead>
                    <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                        <th className="px-3 py-2">N.°</th>
                        <th className="px-3 py-2">Fecha</th>
                        <th className="px-3 py-2">Estado</th>
                        <th className="px-3 py-2">Ítems</th>
                        <th className="px-3 py-2 text-right">Total</th>
                        <th className="px-3 py-2" />
                    </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                    {isLoading ? (
                        <tr>
                            <td colSpan={6} className="px-3 py-6 text-center text-slate-500">
                                Cargando ventas...
                            </td>
                        </tr>
                    ) : sales.length === 0 ? (
                        <tr>
                            <td colSpan={6} className="px-3 py-8 text-center text-slate-500">
                                Aún no hay ventas registradas para este cliente.
                            </td>
                        </tr>
                    ) : (
                        sales.map((sale) => (
                            <tr key={sale.id}>
                                <td className="px-3 py-3 font-semibold text-slate-900">#{sale.number}</td>
                                <td className="px-3 py-3 text-slate-600">{fmtDate(sale.created_at)}</td>
                                <td className="px-3 py-3">
                                    <span
                                        className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${saleStatusStyles[sale.status] ?? 'bg-slate-100 text-slate-700'}`}
                                    >
                                        {sale.status_label}
                                    </span>
                                </td>
                                <td className="px-3 py-3 text-slate-600">{sale.items_count ?? '—'}</td>
                                <td className="px-3 py-3 text-right font-semibold text-slate-900">
                                    {formatCurrencySmart(sale.total)}
                                </td>
                                <td className="px-3 py-3 text-right">
                                    <Link
                                        href={`/app/gestion/ventas/${sale.id}` as any}
                                        className="text-xs font-semibold text-slate-500 hover:text-slate-900"
                                    >
                                        Ver
                                    </Link>
                                </td>
                            </tr>
                        ))
                    )}
                </tbody>
            </table>
        </div>
    );
}

// ── Quotes tab ────────────────────────────────────────────────────────────────

type QuotesTabProps = {
    quotes: import('@/features/gestion/types').Quote[];
    isLoading: boolean;
    total: number;
};

function QuotesTab({ quotes, isLoading, total }: QuotesTabProps) {
    return (
        <div className="overflow-x-auto">
            <p className="mb-3 text-xs uppercase tracking-wide text-slate-400">{total} presupuestos</p>
            <table className="min-w-full divide-y divide-slate-100 text-sm">
                <thead>
                    <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                        <th className="px-3 py-2">N.°</th>
                        <th className="px-3 py-2">Fecha</th>
                        <th className="px-3 py-2">Estado</th>
                        <th className="px-3 py-2">Ítems</th>
                        <th className="px-3 py-2 text-right">Total</th>
                        <th className="px-3 py-2" />
                    </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                    {isLoading ? (
                        <tr>
                            <td colSpan={6} className="px-3 py-6 text-center text-slate-500">
                                Cargando presupuestos...
                            </td>
                        </tr>
                    ) : quotes.length === 0 ? (
                        <tr>
                            <td colSpan={6} className="px-3 py-8 text-center text-slate-500">
                                Aún no hay presupuestos registrados para este cliente.
                            </td>
                        </tr>
                    ) : (
                        quotes.map((quote) => (
                            <tr key={quote.id}>
                                <td className="px-3 py-3 font-semibold text-slate-900">{quote.number}</td>
                                <td className="px-3 py-3 text-slate-600">{fmtDate(quote.created_at)}</td>
                                <td className="px-3 py-3">
                                    <span
                                        className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${quoteStatusStyles[quote.status] ?? 'bg-slate-100 text-slate-700'}`}
                                    >
                                        {quote.status_label}
                                    </span>
                                </td>
                                <td className="px-3 py-3 text-slate-600">{quote.items_count ?? '—'}</td>
                                <td className="px-3 py-3 text-right font-semibold text-slate-900">
                                    {formatCurrencySmart(quote.total)}
                                </td>
                                <td className="px-3 py-3 text-right">
                                    <Link
                                        href={`/app/gestion/ventas/presupuestos/${quote.id}` as any}
                                        className="text-xs font-semibold text-slate-500 hover:text-slate-900"
                                    >
                                        Ver
                                    </Link>
                                </td>
                            </tr>
                        ))
                    )}
                </tbody>
            </table>
        </div>
    );
}
