import Link from 'next/link';
import type { ReactNode } from 'react';

import type { CashClosureDetail } from '@/features/reports/types';
import { formatCurrency } from '@/lib/format';

type CashSessionDetailViewProps = {
    closure: CashClosureDetail;
    backHref: string;
    backLabel?: string;
    contextLabel?: string;
    actionsSlot?: ReactNode;
    saleDetailHref?: (saleId: string) => string;
    paymentsSaleHref?: (saleId: string) => string;
};

export function CashSessionDetailView({
    closure,
    backHref,
    backLabel = '← Volver',
    contextLabel = 'Caja',
    actionsSlot,
    saleDetailHref,
    paymentsSaleHref,
}: CashSessionDetailViewProps) {
    const difference = Number(closure.difference ?? 0);
    const openerName = closure.opened_by_name || closure.opened_by?.name || '—';
    const sales = closure.sales ?? [];
    const productsSummary = closure.products_summary ?? [];
    const cashSales = closure.cash_sales ?? [];
    const movements = closure.movements ?? [];

    return (
        <section className="space-y-6">
            <div className="flex items-center gap-3 text-sm text-slate-500">
                <Link href={backHref} className="font-semibold text-slate-600 hover:text-slate-900">
                    {backLabel}
                </Link>
                <span>/</span>
                <p>{closure.register?.name ?? 'Caja sin nombre'}</p>
            </div>

            <header className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                    <div>
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-400">{contextLabel}</p>
                        <h1 className="text-3xl font-semibold text-slate-900">{closure.register?.name ?? 'Caja'}</h1>
                        <p className="text-sm text-slate-500">
                            Apertura {formatDate(closure.opened_at)} •{' '}
                            {closure.closed_at ? `Cierre ${formatDate(closure.closed_at)}` : 'Sesión abierta'}
                        </p>
                    </div>
                    <div className="flex flex-col items-end gap-3 md:flex-row md:items-center">
                        {actionsSlot}
                        <div className="text-right">
                            <p className="text-sm font-medium text-slate-500">Diferencia</p>
                            <p className={`text-2xl font-semibold ${difference === 0 ? 'text-slate-900' : difference > 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                                {formatCurrency(difference)}
                            </p>
                            <p className="text-xs text-slate-500">
                                Contado: {formatCurrency(closure.counted_cash)} • Esperado: {formatCurrency(closure.expected_breakdown.expected_cash)}
                            </p>
                        </div>
                    </div>
                </div>
                <dl className="mt-6 grid gap-4 text-sm text-slate-600 md:grid-cols-3">
                    <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-400">Abrió</dt>
                        <dd className="text-base font-semibold text-slate-900">{openerName}</dd>
                    </div>
                    <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-400">Cerró</dt>
                        <dd className="text-base font-semibold text-slate-900">{closure.closed_by?.name ?? '—'}</dd>
                    </div>
                    <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-400">Estado</dt>
                        <dd className={`text-base font-semibold ${closure.status === 'closed' ? 'text-emerald-600' : 'text-amber-600'}`}>
                            {closure.status === 'closed' ? 'Cerrada' : 'Abierta'}
                        </dd>
                    </div>
                </dl>
                {closure.note ? <p className="mt-4 rounded-2xl bg-slate-50 p-4 text-sm text-slate-600">{closure.note}</p> : null}
            </header>

            <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="text-lg font-semibold text-slate-900">Composición esperada</h2>
                <div className="mt-4 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {Object.entries(closure.expected_breakdown).map(([key, value]) => (
                        <div key={key} className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                            <p className="text-xs uppercase tracking-wide text-slate-400">{breakdownLabel[key] ?? key}</p>
                            <p className="text-2xl font-semibold text-slate-900">{formatCurrency(value)}</p>
                        </div>
                    ))}
                </div>
            </section>

            <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-4">
                    <h2 className="text-lg font-semibold text-slate-900">Pagos en efectivo</h2>
                    <p className="text-sm text-slate-500">Total: {formatCurrency(closure.payments_summary.payments_total)}</p>
                </div>
                <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    {Object.entries(closure.payments_summary.payments_by_method).map(([method, total]) => (
                        <div key={method} className="rounded-2xl border border-slate-100 bg-white p-4">
                            <p className="text-xs uppercase tracking-wide text-slate-400">{methodLabel(method)}</p>
                            <p className="text-xl font-semibold text-slate-900">{formatCurrency(total)}</p>
                        </div>
                    ))}
                </div>

                <div className="mt-6 overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-100 text-sm">
                        <thead>
                            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                                <th className="px-3 py-2">Venta</th>
                                <th className="px-3 py-2">Cliente</th>
                                <th className="px-3 py-2">Fecha</th>
                                <th className="px-3 py-2 text-right">Monto</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {cashSales.map((sale) => (
                                <tr key={sale.id}>
                                    <td className="px-3 py-3 font-semibold text-slate-900">
                                        {renderSaleLink(paymentsSaleHref, sale.sale_id, `#${sale.sale_number}`)}
                                    </td>
                                    <td className="px-3 py-3 text-slate-600">{sale.customer_name ?? 'Mostrador'}</td>
                                    <td className="px-3 py-3 text-slate-600">{formatDate(sale.created_at)}</td>
                                    <td className="px-3 py-3 text-right font-semibold text-slate-900">{formatCurrency(sale.amount)}</td>
                                </tr>
                            ))}
                            {!cashSales.length && (
                                <tr>
                                    <td colSpan={4} className="px-3 py-4 text-center text-slate-400">
                                        Sin ventas en efectivo.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </section>

            <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="text-lg font-semibold text-slate-900">Ventas del turno</h2>
                <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-100 text-sm">
                        <thead>
                            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                                <th className="px-3 py-2">Venta</th>
                                <th className="px-3 py-2">Cliente</th>
                                <th className="px-3 py-2">Estado</th>
                                <th className="px-3 py-2">Pago</th>
                                <th className="px-3 py-2 text-right">Total</th>
                                <th className="px-3 py-2 text-right">Pagado</th>
                                <th className="px-3 py-2 text-right">Saldo</th>
                                <th className="px-3 py-2">Fecha</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {sales.map((sale) => (
                                <tr key={sale.id}>
                                    <td className="px-3 py-3 font-semibold text-slate-900">
                                        {renderSaleLink(saleDetailHref, sale.id, `#${sale.number}`)}
                                    </td>
                                    <td className="px-3 py-3 text-slate-600">{sale.customer_name || 'Mostrador'}</td>
                                    <td className="px-3 py-3">
                                        <span className={saleStatusClass(sale.status)}>{sale.status_label}</span>
                                    </td>
                                    <td className="px-3 py-3 text-slate-600">{sale.payment_method_label}</td>
                                    <td className="px-3 py-3 text-right font-semibold text-slate-900">{formatCurrency(sale.total)}</td>
                                    <td className="px-3 py-3 text-right text-slate-700">{formatCurrency(sale.paid_total)}</td>
                                    <td className={`px-3 py-3 text-right font-semibold ${Number(sale.balance) === 0 ? 'text-slate-500' : 'text-amber-600'}`}>
                                        {formatCurrency(sale.balance)}
                                    </td>
                                    <td className="px-3 py-3 text-slate-600">{formatDate(sale.created_at)}</td>
                                </tr>
                            ))}
                            {!sales.length && (
                                <tr>
                                    <td colSpan={8} className="px-3 py-4 text-center text-slate-400">
                                        Sin ventas registradas en esta sesión.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </section>

            <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="text-lg font-semibold text-slate-900">Productos vendidos</h2>
                <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-100 text-sm">
                        <thead>
                            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                                <th className="px-3 py-2">Producto</th>
                                <th className="px-3 py-2 text-right">Cantidad</th>
                                <th className="px-3 py-2 text-right">Ventas</th>
                                <th className="px-3 py-2 text-right">Total</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {productsSummary.map((product) => (
                                <tr key={`${product.product_id ?? product.name}`}>
                                    <td className="px-3 py-3 font-semibold text-slate-900">{product.name}</td>
                                    <td className="px-3 py-3 text-right text-slate-600">{product.quantity}</td>
                                    <td className="px-3 py-3 text-right text-slate-600">{product.sales_count}</td>
                                    <td className="px-3 py-3 text-right font-semibold text-slate-900">{formatCurrency(product.amount_total)}</td>
                                </tr>
                            ))}
                            {!productsSummary.length && (
                                <tr>
                                    <td colSpan={4} className="px-3 py-4 text-center text-slate-400">
                                        Sin productos vendidos en esta sesión.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </section>

            <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="text-lg font-semibold text-slate-900">Movimientos manuales</h2>
                <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-100 text-sm">
                        <thead>
                            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                                <th className="px-3 py-2">Fecha</th>
                                <th className="px-3 py-2">Tipo</th>
                                <th className="px-3 py-2">Categoría</th>
                                <th className="px-3 py-2">Nota</th>
                                <th className="px-3 py-2 text-right">Monto</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {movements.map((movement) => (
                                <tr key={movement.id}>
                                    <td className="px-3 py-3 text-slate-600">{formatDate(movement.created_at)}</td>
                                    <td className="px-3 py-3 font-semibold text-slate-900">{movementTypeLabel(movement.movement_type)}</td>
                                    <td className="px-3 py-3 text-slate-600">{movement.category}</td>
                                    <td className="px-3 py-3 text-slate-600">{movement.note || '—'}</td>
                                    <td className={`px-3 py-3 text-right font-semibold ${movement.movement_type === 'in' ? 'text-emerald-600' : 'text-rose-600'}`}>
                                        {movement.movement_type === 'in' ? '+' : '-'}
                                        {formatCurrency(movement.amount)}
                                    </td>
                                </tr>
                            ))}
                            {!movements.length && (
                                <tr>
                                    <td colSpan={5} className="px-3 py-4 text-center text-slate-400">
                                        Sin movimientos manuales.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </section>
        </section>
    );
}

const breakdownLabel: Record<string, string> = {
    saldo_inicial: 'Saldo inicial',
    cash_sales_total: 'Ventas en efectivo',
    movements_in_total: 'Ingresos manuales',
    movements_out_total: 'Egresos manuales',
    expected_cash: 'Efectivo esperado',
};

function renderSaleLink(builder: ((id: string) => string) | undefined, id: string, label: string) {
    if (!builder) {
        return label;
    }
    return (
        <Link href={builder(id)} className="underline-offset-4 hover:underline">
            {label}
        </Link>
    );
}

function formatDate(value: string) {
    return new Intl.DateTimeFormat('es-AR', {
        dateStyle: 'medium',
        timeStyle: 'short',
    }).format(new Date(value));
}

function methodLabel(method: string) {
    const labels: Record<string, string> = {
        cash: 'Efectivo',
        card: 'Tarjeta',
        card_debit: 'Tarjeta débito',
        card_credit: 'Tarjeta crédito',
        transfer: 'Transferencia',
        wallet: 'Billetera',
        account: 'Cuenta corriente',
    };
    return labels[method] ?? method;
}

function movementTypeLabel(type: 'in' | 'out') {
    return type === 'in' ? 'Ingreso' : 'Egreso';
}

function saleStatusClass(status: string) {
    const base = 'inline-flex rounded-full px-3 py-1 text-xs font-semibold';
    if (status === 'cancelled') {
        return `${base} bg-rose-50 text-rose-700 border border-rose-100`;
    }
    return `${base} bg-emerald-50 text-emerald-700 border border-emerald-100`;
}
