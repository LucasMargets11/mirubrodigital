import { formatCurrency, formatDateTime, getSaleBalanceValue, isSaleFullyPaid } from '../utils';
import type { SalesWithBalance } from '../types';

type FilterValue = 'pending' | 'paid' | 'all';

type SalesToCollectTableProps = {
    sales: SalesWithBalance[];
    loading?: boolean;
    canCollect: boolean;
    filter: FilterValue;
    onFilterChange: (value: FilterValue) => void;
    onCollect: (sale: SalesWithBalance) => void;
};

const FILTER_LABELS: Record<FilterValue, string> = {
    pending: 'Pendientes',
    paid: 'Pagadas',
    all: 'Todas',
};

export function SalesToCollectTable({ sales, loading, canCollect, filter, onCollect, onFilterChange }: SalesToCollectTableProps) {
    const filteredSales = sales.filter((sale) => {
        if (filter === 'all') {
            return true;
        }
        const isPaid = isSaleFullyPaid(sale);
        return filter === 'paid' ? isPaid : !isPaid;
    });

    return (
        <section className="space-y-4 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <header className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Ventas del día</p>
                    <h3 className="text-xl font-semibold text-slate-900">Cobros rápidos</h3>
                </div>
                <div className="flex gap-2">
                    {(Object.keys(FILTER_LABELS) as FilterValue[]).map((value) => (
                        <button
                            key={value}
                            type="button"
                            onClick={() => onFilterChange(value)}
                            className={`rounded-full px-4 py-1 text-sm font-semibold transition ${filter === value
                                    ? 'bg-slate-900 text-white'
                                    : 'border border-slate-200 bg-white text-slate-600 hover:border-slate-900 hover:text-slate-900'
                                }`}
                        >
                            {FILTER_LABELS[value]}
                        </button>
                    ))}
                </div>
            </header>
            <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-100 text-sm">
                    <thead>
                        <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
                            <th className="px-3 py-2">Venta</th>
                            <th className="px-3 py-2">Cliente</th>
                            <th className="px-3 py-2">Fecha</th>
                            <th className="px-3 py-2 text-right">Total</th>
                            <th className="px-3 py-2 text-right">Pagado</th>
                            <th className="px-3 py-2 text-right">Saldo</th>
                            <th className="px-3 py-2" />
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                        {loading ? (
                            <tr>
                                <td colSpan={7} className="px-3 py-6 text-center text-slate-500">
                                    Cargando ventas...
                                </td>
                            </tr>
                        ) : null}
                        {!loading && filteredSales.length === 0 ? (
                            <tr>
                                <td colSpan={7} className="px-3 py-6 text-center text-slate-500">
                                    {sales.length === 0 ? 'Aún no registraste ventas hoy.' : 'No hay ventas en este estado.'}
                                </td>
                            </tr>
                        ) : null}
                        {filteredSales.map((sale) => {
                            const balanceValue = getSaleBalanceValue(sale);
                            const paid = Number(sale.paid_total ?? '0');
                            const isPaid = isSaleFullyPaid(sale);
                            return (
                                <tr key={sale.id} className="hover:bg-slate-50">
                                    <td className="px-3 py-3 font-semibold text-slate-900">#{sale.number}</td>
                                    <td className="px-3 py-3">
                                        <p className="font-medium text-slate-900">{sale.customer_name ?? sale.customer?.name ?? 'Sin cliente'}</p>
                                        {sale.notes ? <p className="text-xs text-slate-400 line-clamp-1">{sale.notes}</p> : null}
                                    </td>
                                    <td className="px-3 py-3 text-slate-500">{formatDateTime(sale.created_at)}</td>
                                    <td className="px-3 py-3 text-right font-semibold text-slate-900">{formatCurrency(sale.total)}</td>
                                    <td className="px-3 py-3 text-right text-emerald-600">{formatCurrency(paid)}</td>
                                    <td className={`px-3 py-3 text-right font-semibold ${isPaid ? 'text-emerald-600' : 'text-rose-600'}`}>
                                        {formatCurrency(balanceValue)}
                                    </td>
                                    <td className="px-3 py-3 text-right">
                                        <button
                                            type="button"
                                            onClick={() => onCollect(sale)}
                                            disabled={!canCollect || isPaid}
                                            className="rounded-full border border-slate-200 px-4 py-1 text-sm font-semibold text-slate-600 transition hover:border-slate-900 hover:text-slate-900 disabled:cursor-not-allowed disabled:border-slate-300 disabled:text-slate-300"
                                        >
                                            Cobrar
                                        </button>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </section>
    );
}
