import { formatCurrency, getMethodLabel } from '../utils';
import type { CashPaymentMethod, CashSession } from '../types';

type CashSummaryCardsProps = {
    session: CashSession | null | undefined;
    loading?: boolean;
};

export function CashSummaryCards({ session, loading }: CashSummaryCardsProps) {
    const totals = session?.totals;

    if (loading) {
        return (
            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <p className="text-sm text-slate-500">Calculando resumen...</p>
            </div>
        );
    }

    if (!session || !totals) {
        return (
            <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-500 shadow-sm">
                Abrí una caja para ver el resumen operativo.
            </div>
        );
    }

    const methodEntries = Object.entries(totals.payments_by_method ?? {});

    return (
        <div className="grid gap-4 lg:grid-cols-4">
            <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Total cobrado</p>
                <p className="mt-2 text-3xl font-semibold text-slate-900">{formatCurrency(totals.payments_total)}</p>
                <p className="text-sm text-slate-500">{totals.sales_count} ventas registradas</p>
            </div>
            <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Movimientos</p>
                <div className="mt-3 space-y-1 text-sm">
                    <p className="flex items-center justify-between text-emerald-600">
                        <span>Ingresos</span>
                        <span className="font-semibold">{formatCurrency(totals.movements_in_total)}</span>
                    </p>
                    <p className="flex items-center justify-between text-rose-600">
                        <span>Egresos</span>
                        <span className="font-semibold">{formatCurrency(totals.movements_out_total)}</span>
                    </p>
                </div>
            </div>
            <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Efectivo esperado</p>
                <p className="mt-2 text-3xl font-semibold text-slate-900">{formatCurrency(totals.cash_expected_total)}</p>
                <p className="text-sm text-slate-500">Saldo inicial {formatCurrency(session.opening_cash_amount)}</p>
            </div>
            <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Cobros por medio</p>
                <div className="mt-3 space-y-1 text-sm">
                    {methodEntries.length === 0 ? (
                        <p className="text-slate-500">Registrá pagos para ver el detalle.</p>
                    ) : (
                        methodEntries.map(([method, amount]) => (
                            <p key={method} className="flex items-center justify-between text-slate-600">
                                <span>{getMethodLabel(method as CashPaymentMethod)}</span>
                                <span className="font-semibold">{formatCurrency(amount)}</span>
                            </p>
                        ))
                    )}
                </div>
            </div>
        </div>
    );
}
