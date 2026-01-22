import Link from 'next/link';
import { notFound, redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { serverApiFetch } from '@/lib/api/server';
import { getSession } from '@/lib/auth';
import { buildInvoicePdfUrl } from '@/features/invoices/api';
import type { Invoice } from '@/features/invoices/types';

function formatCurrency(value: string | number) {
    const numeric = typeof value === 'number' ? value : Number(value);
    return new Intl.NumberFormat('es-AR', {
        style: 'currency',
        currency: 'ARS',
        maximumFractionDigits: 2,
    }).format(Number.isNaN(numeric) ? 0 : numeric);
}

function formatDate(value: string) {
    return new Date(value).toLocaleString('es-AR', { dateStyle: 'full', timeStyle: 'short' });
}

type PageProps = {
    params: {
        id: string;
    };
};

export default async function InvoiceDetailPage({ params }: PageProps) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.invoices !== false;
    const canView = session.permissions?.view_invoices ?? false;

    if (!featureEnabled) {
        return <AccessMessage title="Tu plan no incluye Facturas" description="Actualizá tu plan para ver comprobantes." />;
    }

    if (!canView) {
        return <AccessMessage title="Sin acceso" description="Tu rol no puede ver facturas." hint="Pedí acceso a un administrador" />;
    }

    let invoice: Invoice | null = null;
    try {
        invoice = await serverApiFetch<Invoice>(`/api/v1/invoices/${params.id}/`);
    } catch (error) {
        notFound();
    }

    if (!invoice) {
        notFound();
    }

    return (
        <section className="space-y-6">
            <div className="flex flex-wrap items-center gap-3 text-sm text-slate-500">
                <Link href="/app/gestion/facturas" className="font-semibold text-slate-600 hover:text-slate-900">
                    ← Volver al listado
                </Link>
                <span>/</span>
                <p>Factura {invoice.full_number}</p>
            </div>
            <header className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                    <div>
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Factura</p>
                        <h1 className="text-3xl font-semibold text-slate-900">{invoice.full_number}</h1>
                        <p className="text-sm text-slate-500">Emitida el {formatDate(invoice.issued_at)}</p>
                        <p className="text-sm text-slate-500">Venta asociada #{invoice.sale_number}</p>
                    </div>
                    <div className="flex flex-col items-end gap-3 text-sm">
                        <a
                            href={buildInvoicePdfUrl(invoice.id)}
                            target="_blank"
                            rel="noreferrer"
                            className="rounded-full border border-slate-200 px-4 py-2 font-semibold text-slate-700 hover:border-slate-900 hover:text-slate-900"
                        >
                            Descargar PDF
                        </a>
                        <button
                            type="button"
                            disabled
                            className="rounded-full border border-dashed border-slate-200 px-4 py-2 font-semibold text-slate-400"
                        >
                            Re-enviar (próximamente)
                        </button>
                    </div>
                </div>
                <dl className="mt-6 grid gap-4 text-sm text-slate-600 sm:grid-cols-3">
                    <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-400">Cliente</dt>
                        <dd className="text-base font-semibold text-slate-900">{invoice.customer_name || 'Consumidor final'}</dd>
                    </div>
                    <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-400">Documento</dt>
                        <dd className="text-base font-semibold text-slate-900">{invoice.customer_tax_id || '—'}</dd>
                    </div>
                    <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-400">Dirección</dt>
                        <dd className="text-base font-semibold text-slate-900">{invoice.customer_address || '—'}</dd>
                    </div>
                </dl>
            </header>
            <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex items-center justify-between">
                    <h2 className="text-lg font-semibold text-slate-900">Detalle de ítems</h2>
                    <p className="text-sm text-slate-500">{invoice.items.length} productos</p>
                </div>
                <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-100 text-sm">
                        <thead>
                            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                                <th className="px-3 py-2">Producto</th>
                                <th className="px-3 py-2">Cantidad</th>
                                <th className="px-3 py-2">Precio</th>
                                <th className="px-3 py-2 text-right">Total</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {invoice.items.map((item) => (
                                <tr key={item.id}>
                                    <td className="px-3 py-3">
                                        <p className="font-medium text-slate-900">{item.product_name}</p>
                                    </td>
                                    <td className="px-3 py-3 text-slate-500">{Number(item.quantity).toLocaleString('es-AR')}</td>
                                    <td className="px-3 py-3 text-slate-500">{formatCurrency(item.unit_price)}</td>
                                    <td className="px-3 py-3 text-right font-semibold text-slate-900">{formatCurrency(item.line_total)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                <div className="mt-4 border-t border-slate-100 pt-4 text-right text-sm text-slate-600">
                    <p>
                        Subtotal <span className="font-semibold text-slate-900">{formatCurrency(invoice.subtotal)}</span>
                    </p>
                    <p>
                        Descuento <span className="font-semibold text-slate-900">{formatCurrency(invoice.discount)}</span>
                    </p>
                    <p className="text-lg font-semibold text-slate-900">Total {formatCurrency(invoice.total)}</p>
                    <p className="mt-2 text-xs uppercase tracking-wide text-slate-400">Comprobante no fiscal</p>
                </div>
            </section>
        </section>
    );
}
