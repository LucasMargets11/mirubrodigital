import Link from 'next/link';
import { notFound, redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { serverApiFetch } from '@/lib/api/server';
import { getSession } from '@/lib/auth';
import type { ReportSale } from '@/features/reports/types';
import { formatCurrency, formatNumber } from '@/lib/format';

const statusStyles: Record<string, string> = {
    completed: 'bg-emerald-100 text-emerald-700',
    cancelled: 'bg-rose-100 text-rose-700',
};

type PageProps = {
    params: {
        id: string;
    };
};

export default async function ReportSaleDetailPage({ params }: PageProps) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.reports !== false;
    const canView = session.permissions?.view_reports_sales ?? false;

    if (!featureEnabled) {
        return <AccessMessage title="Tu plan no incluye Reportes" description="Actualizá el plan para ver este detalle." />;
    }

    if (!canView) {
        return <AccessMessage title="Sin acceso" description="Tu rol no puede ver reportes de ventas." hint="Pedí acceso a un administrador" />;
    }

    let sale: ReportSale | null = null;
    try {
        sale = await serverApiFetch<ReportSale>(`/api/v1/reports/sales/${params.id}/`);
    } catch (error) {
        notFound();
    }

    if (!sale) {
        notFound();
    }

    return (
        <section className="space-y-6">
            <div className="flex items-center gap-3 text-sm text-slate-500">
                <Link href="/app/gestion/reportes/ventas" className="font-semibold text-slate-600 hover:text-slate-900">
                    ← Volver a Ventas
                </Link>
                <span>/</span>
                <p>Venta #{sale.number}</p>
            </div>

            <header className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                    <div>
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Venta #{sale.number}</p>
                        <h1 className="text-3xl font-semibold text-slate-900">{formatCurrency(sale.total)}</h1>
                        <p className="text-sm text-slate-500">
                            {new Intl.DateTimeFormat('es-AR', { dateStyle: 'full', timeStyle: 'short' }).format(new Date(sale.created_at))}
                        </p>
                    </div>
                    <div className="flex flex-col items-end gap-2">
                        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusStyles[sale.status] ?? 'bg-slate-100 text-slate-600'}`}>
                            {sale.status_label}
                        </span>
                        <p className="text-sm text-slate-500">{sale.payment_method_label}</p>
                        {sale.cashier && (
                            <p className="text-xs text-slate-500">Cajero: {sale.cashier.name}</p>
                        )}
                    </div>
                </div>
                <dl className="mt-6 grid gap-4 text-sm text-slate-600 sm:grid-cols-3">
                    <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-400">Cliente</dt>
                        <dd className="text-base font-semibold text-slate-900">{sale.customer?.name || sale.customer_name || 'Mostrador'}</dd>
                        {sale.customer?.email && <p className="text-xs text-slate-500">{sale.customer.email}</p>}
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

            <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                        <h2 className="text-lg font-semibold text-slate-900">Pagos</h2>
                        <p className="text-sm text-slate-500">{sale.payments?.length ?? 0} registros</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                        {(sale.payments_summary ?? []).map((payment) => (
                            <span key={payment.method} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
                                {payment.method_label}: {formatCurrency(payment.amount)}
                            </span>
                        ))}
                    </div>
                </div>
                <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-100 text-sm">
                        <thead>
                            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                                <th className="px-3 py-2">Método</th>
                                <th className="px-3 py-2">Referencia</th>
                                <th className="px-3 py-2">Fecha</th>
                                <th className="px-3 py-2 text-right">Monto</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {(sale.payments ?? []).map((payment) => (
                                <tr key={payment.id}>
                                    <td className="px-3 py-3 font-medium text-slate-900">{payment.method_label ?? payment.method}</td>
                                    <td className="px-3 py-3 text-slate-600">{payment.reference || '—'}</td>
                                    <td className="px-3 py-3 text-slate-600">{formatDate(payment.created_at)}</td>
                                    <td className="px-3 py-3 text-right font-semibold text-slate-900">{formatCurrency(payment.amount)}</td>
                                </tr>
                            ))}
                            {!sale.payments?.length && (
                                <tr>
                                    <td colSpan={4} className="px-3 py-4 text-center text-slate-400">
                                        Sin pagos registrados.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </section>

            <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex items-center justify-between">
                    <h2 className="text-lg font-semibold text-slate-900">Detalle de productos</h2>
                    <p className="text-sm text-slate-500">{sale.items?.length ?? 0} ítems</p>
                </div>
                <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-100 text-sm">
                        <thead>
                            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                                <th className="px-3 py-2">Producto</th>
                                <th className="px-3 py-2">Cantidad</th>
                                <th className="px-3 py-2">Precio unitario</th>
                                <th className="px-3 py-2 text-right">Total</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {(sale.items ?? []).map((item) => (
                                <tr key={item.id}>
                                    <td className="px-3 py-3">
                                        <p className="font-medium text-slate-900">{item.product_name}</p>
                                        <p className="text-xs text-slate-400">ID {item.product_id ?? '—'}</p>
                                    </td>
                                    <td className="px-3 py-3 text-slate-600">{formatNumber(item.quantity)}</td>
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

function formatDate(value: string) {
    return new Intl.DateTimeFormat('es-AR', {
        dateStyle: 'medium',
        timeStyle: 'short',
    }).format(new Date(value));
}
