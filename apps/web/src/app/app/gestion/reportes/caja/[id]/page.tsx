import Link from 'next/link';
import { notFound, redirect } from 'next/navigation';

import { AccessMessage } from '@/components/app/access-message';
import { serverApiFetch } from '@/lib/api/server';
import { getSession } from '@/lib/auth';
import type { CashClosureDetail } from '@/features/reports/types';
import { formatCurrency } from '@/lib/format';

type PageProps = {
    params: {
        id: string;
    };
};

export default async function CashClosureDetailPage({ params }: PageProps) {
    const session = await getSession();

    if (!session) {
        redirect('/entrar');
    }

    const featureEnabled = session.features?.reports !== false;
    const canView = session.permissions?.view_reports_cash ?? false;

    if (!featureEnabled) {
        return <AccessMessage title="Tu plan no incluye Reportes" description="Actualizá el plan para ver cierres de caja." />;
    }

    if (!canView) {
        return <AccessMessage title="Sin acceso" description="Tu rol no puede ver reportes de caja." hint="Pedí acceso a un administrador" />;
    }

    let closure: CashClosureDetail | null = null;
    try {
        closure = await serverApiFetch<CashClosureDetail>(`/api/v1/reports/cash/closures/${params.id}/`);
    } catch (error) {
        notFound();
    }

    if (!closure) {
        notFound();
    }

    const difference = Number(closure.difference ?? 0);

    return (
        <section className="space-y-6">
            <div className="flex items-center gap-3 text-sm text-slate-500">
                <Link href="/app/gestion/reportes/caja" className="font-semibold text-slate-600 hover:text-slate-900">
                    ← Volver a Cierres
                </Link>
                <span>/</span>
                <p>{closure.register?.name ?? 'Caja sin nombre'}</p>
            </div>

            <header className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                    <div>
                        <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Caja</p>
                        <h1 className="text-3xl font-semibold text-slate-900">{closure.register?.name ?? 'Caja'}</h1>
                        <p className="text-sm text-slate-500">
                            Apertura {formatDate(closure.opened_at)} • {closure.closed_at ? `Cierre ${formatDate(closure.closed_at)}` : 'Sesión abierta'}
                        </p>
                    </div>
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
                <dl className="mt-6 grid gap-4 text-sm text-slate-600 md:grid-cols-3">
                    <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-400">Abrió</dt>
                        <dd className="text-base font-semibold text-slate-900">{closure.opened_by?.name ?? '—'}</dd>
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
                <h2 className="text-lg font-semibold text-slate-900">Pagos en efectivo</h2>
                <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                        <p className="text-xs uppercase tracking-wide text-slate-400">Total pagos</p>
                        <p className="text-2xl font-semibold text-slate-900">{formatCurrency(closure.payments_summary.payments_total)}</p>
                    </div>
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
                            {(closure.cash_sales ?? []).map((sale) => (
                                <tr key={sale.id}>
                                    <td className="px-3 py-3 font-semibold text-slate-900">
                                        <Link href={`/app/gestion/reportes/ventas/${sale.sale_id}`} className="underline-offset-4 hover:underline">
                                            #{sale.sale_number}
                                        </Link>
                                    </td>
                                    <td className="px-3 py-3 text-slate-600">{sale.customer_name ?? 'Mostrador'}</td>
                                    <td className="px-3 py-3 text-slate-600">{formatDate(sale.created_at)}</td>
                                    <td className="px-3 py-3 text-right font-semibold text-slate-900">{formatCurrency(sale.amount)}</td>
                                </tr>
                            ))}
                            {!closure.cash_sales?.length && (
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
                <h2 className="text-lg font-semibold text-slate-900">Movimientos</h2>
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
                            {(closure.movements ?? []).map((movement) => (
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
                            {!closure.movements?.length && (
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
