"use client";

import Link from 'next/link';
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';

import { Modal } from '@/components/ui/modal';
import { buildInvoicePdfUrl } from '@/features/invoices/api';
import { useInvoiceSeries, useIssueInvoice } from '@/features/invoices/hooks';
import { useIssueOrderInvoice } from '@/features/orders/hooks';
import type { SaleInvoiceSummary } from '@/features/gestion/types';

const invoiceStatusLabels: Record<string, string> = {
    issued: 'Emitida',
    voided: 'Anulada',
};

const invoiceStatusStyles: Record<string, string> = {
    issued: 'bg-emerald-100 text-emerald-700',
    voided: 'bg-rose-100 text-rose-700',
};

export type InvoiceActionsProps = {
    entityType: 'sale' | 'order';
    entityId: string;
    entityNumber: number;
    customerName?: string | null;
    existingInvoice?: SaleInvoiceSummary | null;
    featureEnabled: boolean;
    canIssue: boolean;
    canViewInvoices: boolean;
    disabledReason?: string | null;
};

type FormState = {
    series_code: string;
    customer_name: string;
    customer_tax_id: string;
    customer_address: string;
};

export function InvoiceActions({
    entityType,
    entityId,
    entityNumber,
    customerName,
    existingInvoice,
    featureEnabled,
    canIssue,
    canViewInvoices,
    disabledReason,
}: InvoiceActionsProps) {
    const router = useRouter();
    const [open, setOpen] = useState(false);
    const [formError, setFormError] = useState<string | null>(null);
    const [form, setForm] = useState<FormState>({
        series_code: '',
        customer_name: customerName ?? '',
        customer_tax_id: '',
        customer_address: '',
    });

    const invoiceSeriesQuery = useInvoiceSeries();
    const issueSaleInvoiceMutation = useIssueInvoice();
    const issueOrderInvoiceMutation = useIssueOrderInvoice();

    const availableSeries = invoiceSeriesQuery.data ?? [];
    const defaultSeries = useMemo(
        () => availableSeries.find((serie) => serie.is_active)?.code ?? availableSeries[0]?.code ?? '',
        [availableSeries],
    );

    useEffect(() => {
        if (!open) {
            return;
        }
        if (!form.series_code && defaultSeries) {
            setForm((prev) => ({ ...prev, series_code: defaultSeries }));
        }
    }, [open, defaultSeries, form.series_code]);

    const handleChange = (field: keyof FormState, value: string) => {
        setForm((prev) => ({
            ...prev,
            [field]: value,
        }));
    };

    const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        setFormError(null);
        const basePayload = {
            series_code: form.series_code || undefined,
            customer_name: form.customer_name || undefined,
            customer_tax_id: form.customer_tax_id || undefined,
            customer_address: form.customer_address || undefined,
        };
        const onSuccess = () => {
            setOpen(false);
            setFormError(null);
            router.refresh();
        };
        const onError = () => {
            setFormError('No pudimos generar la factura. Intentá nuevamente.');
        };
        if (entityType === 'order') {
            issueOrderInvoiceMutation.mutate(
                { orderId: entityId, payload: basePayload },
                { onSuccess, onError },
            );
            return;
        }
        issueSaleInvoiceMutation.mutate(
            {
                sale_id: entityId,
                ...basePayload,
            },
            { onSuccess, onError },
        );
    };

    if (!featureEnabled) {
        return (
            <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="text-lg font-semibold text-slate-900">Facturas digitales</h2>
                <p className="mt-2 text-sm text-slate-500">
                    Tu plan actual no incluye los comprobantes digitales. Actualizá para emitir facturas desde las {entityType === 'order' ? 'órdenes' : 'ventas'}.
                </p>
            </section>
        );
    }

    const contextLabel = entityType === 'order' ? 'orden' : 'venta';
    const isIssuing = entityType === 'order' ? issueOrderInvoiceMutation.isPending : issueSaleInvoiceMutation.isPending;
    const buttonDisabled = existingInvoice ? false : !canIssue || Boolean(disabledReason);

    return (
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div>
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Facturación digital</p>
                    <h2 className="text-xl font-semibold text-slate-900">
                        {existingInvoice ? 'Factura emitida' : `Generá la factura de la ${contextLabel}`}
                    </h2>
                    <p className="text-sm text-slate-500">Factura vinculada a la {contextLabel} #{entityNumber}.</p>
                </div>
                <div className="flex flex-col gap-3 text-sm font-semibold text-slate-700 md:flex-row">
                    {existingInvoice ? (
                        <>
                            {canViewInvoices ? (
                                <Link
                                    href={`/app/gestion/facturas/${existingInvoice.id}`}
                                    className="rounded-full border border-slate-200 px-4 py-2 text-center hover:border-slate-900 hover:text-slate-900"
                                >
                                    Ver detalle
                                </Link>
                            ) : null}
                            <a
                                href={buildInvoicePdfUrl(existingInvoice.id)}
                                target="_blank"
                                rel="noreferrer"
                                className="rounded-full border border-slate-200 px-4 py-2 text-center hover:border-slate-900 hover:text-slate-900"
                            >
                                Descargar PDF
                            </a>
                        </>
                    ) : (
                        <button
                            type="button"
                            onClick={() => setOpen(true)}
                            disabled={buttonDisabled}
                            className="rounded-full border border-slate-200 px-5 py-2 text-center font-semibold transition hover:border-slate-900 hover:text-slate-900 disabled:cursor-not-allowed disabled:border-slate-100 disabled:text-slate-300"
                        >
                            {disabledReason ? 'No disponible' : 'Generar factura'}
                        </button>
                    )}
                </div>
            </div>
            {existingInvoice ? (
                <div className="mt-4 flex flex-col gap-3 rounded-2xl border border-slate-100 bg-slate-50 p-4 md:flex-row md:items-center md:justify-between">
                    <div>
                        <p className="text-sm text-slate-500">Comprobante emitido</p>
                        <p className="text-lg font-semibold text-slate-900">{existingInvoice.full_number}</p>
                    </div>
                    <span className={`self-start rounded-full px-3 py-1 text-xs font-semibold ${invoiceStatusStyles[existingInvoice.status] ?? 'bg-slate-200 text-slate-700'}`}>
                        {invoiceStatusLabels[existingInvoice.status] ?? existingInvoice.status}
                    </span>
                </div>
            ) : (
                <p className="mt-4 text-sm text-slate-500">
                    Se generará una factura con los productos de la {contextLabel}. Es un comprobante digital interno, no fiscal.
                </p>
            )}
            {(!canIssue || disabledReason) && !existingInvoice ? (
                <p className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-700">
                    {disabledReason || 'No tenés permiso para generar facturas. Pedí acceso a un administrador.'}
                </p>
            ) : null}
            <Modal open={open} title="Generar factura" onClose={() => setOpen(false)}>
                <form className="space-y-4" onSubmit={handleSubmit}>
                    {invoiceSeriesQuery.isError ? (
                        <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
                            No pudimos cargar las series disponibles. Reintentá más tarde.
                        </p>
                    ) : null}
                    <label className="block text-sm font-semibold text-slate-700">
                        Serie <span className="text-rose-600" aria-hidden="true">*</span>
                        <span className="sr-only">Campo obligatorio</span>
                        <select
                            value={form.series_code}
                            onChange={(event) => handleChange('series_code', event.target.value)}
                            className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
                            required
                            aria-required="true"
                        >
                            <option value="">Seleccionar serie</option>
                            {availableSeries.map((serie) => (
                                <option key={serie.id} value={serie.code}>
                                    {serie.prefix ? `${serie.prefix} - ` : ''}
                                    {serie.code} (#{serie.next_number})
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className="block text-sm font-semibold text-slate-700">
                        Nombre o razón social
                        <input
                            type="text"
                            value={form.customer_name}
                            onChange={(event) => handleChange('customer_name', event.target.value)}
                            placeholder="Consumidor final"
                            className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        />
                    </label>
                    <label className="block text-sm font-semibold text-slate-700">
                        CUIT / Documento
                        <input
                            type="text"
                            value={form.customer_tax_id}
                            onChange={(event) => handleChange('customer_tax_id', event.target.value)}
                            className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        />
                    </label>
                    <label className="block text-sm font-semibold text-slate-700">
                        Dirección
                        <input
                            type="text"
                            value={form.customer_address}
                            onChange={(event) => handleChange('customer_address', event.target.value)}
                            className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        />
                    </label>
                    {formError ? (
                        <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">{formError}</p>
                    ) : null}
                    <div className="flex items-center justify-end gap-3">
                        <button
                            type="button"
                            onClick={() => setOpen(false)}
                            className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900"
                        >
                            Cancelar
                        </button>
                        <button
                            type="submit"
                            disabled={isIssuing || !form.series_code}
                            className="rounded-full border border-slate-900 bg-slate-900 px-5 py-2 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-200"
                        >
                            {isIssuing ? 'Generando...' : 'Confirmar emisión'}
                        </button>
                    </div>
                </form>
            </Modal>
        </section>
    );
}
