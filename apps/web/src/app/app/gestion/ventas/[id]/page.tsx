import Link from 'next/link';
import { notFound, redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { serverApiFetch } from '@/lib/api/server';
import { getSession } from '@/lib/auth';
import type { Sale } from '@/features/gestion/types';

import { InvoiceActions } from '../invoice-actions';

function formatCurrency(value: string | number) {
    const numeric = typeof value === 'number' ? value : Number(value);
    return new Intl.NumberFormat('es-AR', {
        style: 'currency',
        currency: 'ARS',
        maximumFractionDigits: 2,
    }).format(Number.isNaN(numeric) ? 0 : numeric);
}

const statusStyles: Record<string, string> = {
    completed: 'bg-emerald-100 text-emerald-700',
    cancelled: 'bg-rose-100 text-rose-700',
};

type PageProps = {
    params: {
        id: string;
    };
};

export default async function SaleDetailPage({ params }: PageProps) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.sales !== false;
    const canView = session.permissions?.view_sales ?? false;
    const invoicesFeatureEnabled = session.features?.invoices !== false;
    const canViewInvoices = session.permissions?.view_invoices ?? false;
    const canIssueInvoices = session.permissions?.issue_invoices ?? false;

    if (!featureEnabled) {
        return <AccessMessage title="Tu plan no incluye Ventas" description="Actualizá el plan para ver esta venta." />;
    }

    if (!canView) {
        return <AccessMessage title="Sin acceso" description="Tu rol no puede ver las ventas." hint="Pedí acceso a un administrador" />;
    }

    let sale: Sale | null = null;
    try {
        sale = await serverApiFetch<Sale>(`/api/v1/sales/${params.id}/`);
    } catch (error) {
        notFound();
    }

    if (!sale) {
        notFound();
    }

    return (
        <section className="space-y-6">
            <div className="flex items-center gap-3 text-sm text-slate-500">
                <Link href="/app/gestion/ventas" className="font-semibold text-slate-600 hover:text-slate-900">
                    ← Volver al listado
                </Link>
                <span>/</span>
                <p>Venta #{sale.number}</p>
            </div>
            <header className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Venta #{sale.number}</p>
                        <h1 className="text-2xl font-semibold text-slate-900">{formatCurrency(sale.total)}</h1>
                        <p className="text-sm text-slate-500">
                            {new Date(sale.created_at).toLocaleString('es-AR', { dateStyle: 'full', timeStyle: 'short' })}
                        </p>
                    </div>
                    <div className="flex flex-col items-end gap-2">
                        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusStyles[sale.status] ?? 'bg-slate-100 text-slate-600'}`}>
                            {sale.status_label}
                        </span>
                        <p className="text-sm text-slate-500">{sale.payment_method_label}</p>
                    </div>
                </div>
                <dl className="mt-6 grid gap-4 text-sm text-slate-600 sm:grid-cols-3">
                    <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-400">Cliente</dt>
                        <dd className="text-base font-semibold text-slate-900">{sale.customer?.name || sale.customer_name || 'Sin cliente'}</dd>
                        {sale.customer && (sale.customer.doc_number || sale.customer.email || sale.customer.phone) ? (
                            <p className="text-xs text-slate-500">
                                {sale.customer.doc_number
                                    ? `${sale.customer.doc_type?.toUpperCase() ?? ''} ${sale.customer.doc_number}`.trim()
                                    : sale.customer.email || sale.customer.phone}
                            </p>
                        ) : null}
                    </div>
                    <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-400">Subtotal</dt>
                        <dd className="text-base font-semibold text-slate-900">{formatCurrency(sale.subtotal)}</dd>
                    </div>
                    <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-400">Descuento</dt>
                        <dd className="text-base font-semibold text-slate-900">{formatCurrency(sale.discount)}</dd>
                    </div>
                </dl>
                {sale.notes ? <p className="mt-4 rounded-2xl bg-slate-50 p-4 text-sm text-slate-600">{sale.notes}</p> : null}
            </header>
            <InvoiceActions
                saleId={sale.id}
                saleNumber={sale.number}
                customerName={sale.customer?.name || sale.customer_name}
                existingInvoice={sale.invoice}
                featureEnabled={invoicesFeatureEnabled}
                canIssue={canIssueInvoices}
                canViewInvoices={canViewInvoices}
            />
            <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex items-center justify-between">
                    <h2 className="text-lg font-semibold text-slate-900">Detalle de items</h2>
                    <p className="text-sm text-slate-500">{sale.items?.length ?? 0} productos</p>
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
                            {(sale.items ?? []).map((item) => (
                                <tr key={item.id}>
                                    <td className="px-3 py-3">
                                        <p className="font-medium text-slate-900">{item.product_name}</p>
                                        <p className="text-xs text-slate-400">ID {item.product_id || '—'}</p>
                                    </td>
                                    <td className="px-3 py-3 text-slate-600">{Number(item.quantity).toLocaleString('es-AR')}</td>
                                    <td className="px-3 py-3 text-slate-600">{formatCurrency(item.unit_price)}</td>
                                    <td className="px-3 py-3 text-right font-semibold text-slate-900">{formatCurrency(item.line_total)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                <div className="mt-4 border-t border-slate-100 pt-4 text-right text-sm text-slate-600">
                    <p>
                        Subtotal <span className="font-semibold text-slate-900">{formatCurrency(sale.subtotal)}</span>
                    </p>
                    <p>
                        Descuento <span className="font-semibold text-slate-900">{formatCurrency(sale.discount)}</span>
                    </p>
                    <p className="text-lg font-semibold text-slate-900">Total {formatCurrency(sale.total)}</p>
                </div>
            </section>
        </section>
    );
}
