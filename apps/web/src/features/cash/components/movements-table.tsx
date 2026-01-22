import { formatCurrency, formatDateTime, getMethodLabel, movementCategoryLabels, movementTypeLabels } from '../utils';
import type { CashMovement } from '../types';

type MovementsTableProps = {
    movements: CashMovement[];
    loading?: boolean;
};

export function MovementsTable({ movements, loading }: MovementsTableProps) {
    return (
        <section className="space-y-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <header>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Historial</p>
                <h3 className="text-xl font-semibold text-slate-900">Movimientos de caja</h3>
            </header>
            <div className="overflow-x-auto text-sm">
                <table className="min-w-full divide-y divide-slate-100">
                    <thead>
                        <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
                            <th className="px-3 py-2">Tipo</th>
                            <th className="px-3 py-2">Categoría</th>
                            <th className="px-3 py-2">Medio</th>
                            <th className="px-3 py-2">Nota</th>
                            <th className="px-3 py-2">Registró</th>
                            <th className="px-3 py-2 text-right">Monto</th>
                            <th className="px-3 py-2">Fecha</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                        {loading ? (
                            <tr>
                                <td colSpan={7} className="px-3 py-6 text-center text-slate-500">
                                    Cargando movimientos...
                                </td>
                            </tr>
                        ) : null}
                        {!loading && movements.length === 0 ? (
                            <tr>
                                <td colSpan={7} className="px-3 py-6 text-center text-slate-500">
                                    Aún no registraste movimientos para esta sesión.
                                </td>
                            </tr>
                        ) : null}
                        {movements.map((movement) => (
                            <tr key={movement.id} className="hover:bg-slate-50">
                                <td className="px-3 py-3 font-semibold text-slate-900">{movementTypeLabels[movement.movement_type]}</td>
                                <td className="px-3 py-3 text-slate-600">{movementCategoryLabels[movement.category]}</td>
                                <td className="px-3 py-3 text-slate-500">{getMethodLabel(movement.method)}</td>
                                <td className="px-3 py-3 text-slate-600">{movement.note || '—'}</td>
                                <td className="px-3 py-3 text-slate-500">{movement.created_by?.name ?? 'Sistema'}</td>
                                <td className="px-3 py-3 text-right font-semibold text-slate-900">{formatCurrency(movement.amount)}</td>
                                <td className="px-3 py-3 text-slate-500">{formatDateTime(movement.created_at)}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </section>
    );
}
