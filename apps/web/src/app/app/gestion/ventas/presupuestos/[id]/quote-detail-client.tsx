"use client";

import Link from 'next/link';
import { useState } from 'react';

import { useQuote, useMarkQuoteSent, useMarkQuoteAccepted, useMarkQuoteRejected } from '@/features/gestion/hooks';
import { getQuotePdfUrl } from '@/features/gestion/api';
import type { QuoteStatus } from '@/features/gestion/types';
import { formatCurrencySmart, formatNumberSmart } from '@/lib/format';

const statusStyles: Record<QuoteStatus, string> = {
    draft: 'bg-slate-100 text-slate-700',
    sent: 'bg-blue-100 text-blue-700',
    accepted: 'bg-emerald-100 text-emerald-700',
    rejected: 'bg-rose-100 text-rose-700',
    expired: 'bg-amber-100 text-amber-700',
    converted: 'bg-violet-100 text-violet-700',
};

type QuoteDetailClientProps = {
    quoteId: string;
    canManage: boolean;
    canSend: boolean;
};

export function QuoteDetailClient({ quoteId, canManage, canSend }: QuoteDetailClientProps) {
    const [feedback, setFeedback] = useState('');
    const quoteQuery = useQuote(quoteId);
    const quote = quoteQuery.data;

    const markSentMutation = useMarkQuoteSent();
    const markAcceptedMutation = useMarkQuoteAccepted();
    const markRejectedMutation = useMarkQuoteRejected();

    const handleDownloadPdf = () => {
        if (!quote) return;
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const url = `${apiUrl}${getQuotePdfUrl(quote.id)}`;
        const link = document.createElement('a');
        link.href = url;
        link.download = `Presupuesto_${quote.number}.pdf`;
        link.target = '_blank';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    const handleMarkSent = async () => {
        if (!quote) return;
        try {
            await markSentMutation.mutateAsync(quote.id);
            setFeedback('Presupuesto marcado como enviado.');
        } catch (error) {
            setFeedback('Error al marcar como enviado.');
        }
    };

    const handleMarkAccepted = async () => {
        if (!quote) return;
        try {
            await markAcceptedMutation.mutateAsync(quote.id);
            setFeedback('Presupuesto marcado como aceptado.');
        } catch (error) {
            setFeedback('Error al marcar como aceptado.');
        }
    };

    const handleMarkRejected = async () => {
        if (!quote) return;
        try {
            await markRejectedMutation.mutateAsync(quote.id);
            setFeedback('Presupuesto marcado como rechazado.');
        } catch (error) {
            setFeedback('Error al marcar como rechazado.');
        }
    };

    if (quoteQuery.isLoading) {
        return (
            <div className="rounded-3xl border border-slate-200 bg-white p-8 text-center shadow-sm">
                <p className="text-slate-500">Cargando presupuesto...</p>
            </div>
        );
    }

    if (quoteQuery.isError || !quote) {
        return (
            <div className="rounded-3xl border border-slate-200 bg-white p-8 text-center shadow-sm">
                <p className="mb-4 text-rose-600">No pudimos cargar el presupuesto.</p>
                <Link
                    href={"/app/gestion/ventas/presupuestos" as any}
                    className="font-semibold text-slate-600 hover:text-slate-900"
                >
                    ← Volver a Presupuestos
                </Link>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <header className="flex flex-col gap-3 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm md:flex-row md:items-center md:justify-between">
                <div>
                    <Link
                        href={"/app/gestion/ventas/presupuestos" as any}
                        className="font-semibold text-slate-600 hover:text-slate-900"
                    >
                        ← Volver a Presupuestos
                    </Link>
                    <h2 className="mt-1 text-2xl font-semibold text-slate-900">
                        Presupuesto {quote.number}
                    </h2>
                    <div className="mt-1 flex items-center gap-2">
                        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusStyles[quote.status]}`}>
                            {quote.status_label}
                        </span>
                        <span className="text-sm text-slate-500">
                            Creado {new Date(quote.created_at).toLocaleDateString('es-AR', { dateStyle: 'long' })}
                        </span>
                    </div>
                </div>
                <div className="flex flex-wrap gap-2">
                    <button
                        onClick={handleDownloadPdf}
                        className="inline-flex items-center justify-center rounded-full border border-slate-300 bg-white px-5 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                    >
                        Descargar PDF
                    </button>
                    {canSend && quote.status === 'draft' && (
                        <button
                            onClick={handleMarkSent}
                            disabled={markSentMutation.isPending}
                            className="inline-flex items-center justify-center rounded-full bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                        >
                            Marcar como enviado
                        </button>
                    )}
                    {canManage && (quote.status === 'sent' || quote.status === 'draft') && (
                        <>
                            <button
                                onClick={handleMarkAccepted}
                                disabled={markAcceptedMutation.isPending}
                                className="inline-flex items-center justify-center rounded-full bg-emerald-600 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
                            >
                                Marcar aceptado
                            </button>
                            <button
                                onClick={handleMarkRejected}
                                disabled={markRejectedMutation.isPending}
                                className="inline-flex items-center justify-center rounded-full bg-rose-600 px-5 py-2 text-sm font-semibold text-white hover:bg-rose-700 disabled:opacity-50"
                            >
                                Marcar rechazado
                            </button>
                        </>
                    )}
                </div>
            </header>

            {feedback && (
                <div className="rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
                    {feedback}
                </div>
            )}

            <div className="grid gap-4 md:grid-cols-2">
                {/* Cliente */}
                <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                    <h3 className="mb-3 text-lg font-semibold text-slate-900">Cliente</h3>
                    <div className="space-y-2 text-sm">
                        <p className="font-medium text-slate-900">
                            {quote.customer?.name || quote.customer_name || 'Sin cliente'}
                        </p>
                        {quote.customer?.doc_number && (
                            <p className="text-slate-600">
                                {quote.customer.doc_type?.toUpperCase()} {quote.customer.doc_number}
                            </p>
                        )}
                        {(quote.customer?.email || quote.customer_email) && (
                            <p className="text-slate-600">{quote.customer?.email || quote.customer_email}</p>
                        )}
                        {(quote.customer?.phone || quote.customer_phone) && (
                            <p className="text-slate-600">{quote.customer?.phone || quote.customer_phone}</p>
                        )}
                    </div>
                </div>

                {/* Detalles */}
                <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                    <h3 className="mb-3 text-lg font-semibold text-slate-900">Detalles</h3>
                    <div className="space-y-2 text-sm">
                        {quote.valid_until && (
                            <div>
                                <span className="font-medium text-slate-700">Válido hasta: </span>
                                <span className="text-slate-600">
                                    {new Date(quote.valid_until).toLocaleDateString('es-AR', { dateStyle: 'long' })}
                                </span>
                            </div>
                        )}
                        {quote.created_by_name && (
                            <div>
                                <span className="font-medium text-slate-700">Creado por: </span>
                                <span className="text-slate-600">{quote.created_by_name}</span>
                            </div>
                        )}
                        <div>
                            <span className="font-medium text-slate-700">Última actualización: </span>
                            <span className="text-slate-600">
                                {new Date(quote.updated_at).toLocaleDateString('es-AR', { dateStyle: 'long' })}
                            </span>
                        </div>
                        {quote.sent_at && (
                            <div>
                                <span className="font-medium text-slate-700">Enviado: </span>
                                <span className="text-slate-600">
                                    {new Date(quote.sent_at).toLocaleDateString('es-AR', { dateStyle: 'long' })}
                                </span>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Items */}
            <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                <h3 className="mb-3 text-lg font-semibold text-slate-900">Items</h3>
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-100 text-sm">
                        <thead>
                            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                                <th className="px-3 py-2">Producto/Descripción</th>
                                <th className="px-3 py-2 text-right">Cant.</th>
                                <th className="px-3 py-2 text-right">Precio Unit.</th>
                                <th className="px-3 py-2 text-right">Descuento</th>
                                <th className="px-3 py-2 text-right">Total</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {quote.items?.map((item) => (
                                <tr key={item.id} className="hover:bg-slate-50">
                                    <td className="px-3 py-3 font-medium text-slate-900">{item.product_name}</td>
                                    <td className="px-4 py-3 text-right text-slate-500">{formatNumberSmart(item.quantity)}</td>
                                    <td className="px-4 py-3 text-right text-slate-500">
                                        {formatCurrencySmart(item.unit_price)}
                                    </td>
                                    <td className="px-4 py-3 text-right text-slate-500">
                                        {Number(item.discount) > 0 ? formatCurrencySmart(item.discount) : '—'}
                                    </td>
                                    <td className="px-4 py-3 text-right font-medium text-slate-900">
                                        {formatCurrencySmart(item.total_line)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Notas y Términos */}
            {(quote.notes || quote.terms) && (
                <div className="grid gap-4 md:grid-cols-2">
                    {quote.notes && (
                        <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                            <h3 className="mb-2 text-lg font-semibold text-slate-900">Notas</h3>
                            <p className="whitespace-pre-wrap text-sm text-slate-600">{quote.notes}</p>
                        </div>
                    )}
                    {quote.terms && (
                        <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                            <h3 className="mb-2 text-lg font-semibold text-slate-900">Términos y condiciones</h3>
                            <p className="whitespace-pre-wrap text-sm text-slate-600">{quote.terms}</p>
                        </div>
                    )}
                </div>
            )}

            {/* Totales */}
            <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                <h3 className="mb-3 text-lg font-semibold text-slate-900">Totales</h3>
                <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                        <span className="text-slate-600">Subtotal:</span>
                        <span className="font-semibold text-slate-900">{formatCurrencySmart(quote.subtotal)}</span>
                    </div>
                    {Number(quote.discount_total) > 0 && (
                        <div className="flex justify-between text-sm">
                            <span className="text-slate-600">Descuentos:</span>
                            <span className="font-semibold text-rose-600">
                                -{formatCurrencySmart(quote.discount_total)}
                            </span>
                        </div>
                    )}
                    {Number(quote.tax_total) > 0 && (
                        <div className="flex justify-between text-sm">
                            <span className="text-slate-600">Impuestos:</span>
                            <span className="font-semibold text-slate-900">{formatCurrencySmart(quote.tax_total)}</span>
                        </div>
                    )}
                    <div className="flex justify-between border-t border-slate-200 pt-2">
                        <span className="text-lg font-semibold text-slate-900">Total:</span>
                        <span className="text-lg font-semibold text-slate-900">{formatCurrencySmart(quote.total)}</span>
                    </div>
                </div>
            </div>
        </div>
    );
}
