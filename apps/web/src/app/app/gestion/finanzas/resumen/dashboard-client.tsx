"use client";

import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import { format, startOfMonth, endOfMonth, isPast, isToday, addDays } from 'date-fns';
import { ArrowUp, ArrowDown, Wallet, Calendar } from 'lucide-react';
import { es } from 'date-fns/locale';
import Link from 'next/link';

import {
    listAccounts, listTransactions, listExpenses,
    listFixedExpenses, getFixedExpensePeriods, FixedExpensePeriod, Expense
} from '@/lib/api/treasury';
import { Currency } from '../components/currency';
import { Loader2 } from 'lucide-react';

export function DashboardClient({ canManage }: { canManage: boolean }) {
    const today = new Date();
    const range = {
        date_from: format(startOfMonth(today), 'yyyy-MM-dd'),
        date_to: format(endOfMonth(today), 'yyyy-MM-dd'),
        limit: 200,
    };

    const { data: accounts, isLoading: isAccountsLoading } = useQuery({ queryKey: ['treasury', 'accounts'], queryFn: listAccounts });
    const { data: transactionsData, isLoading: isTrxLoading } = useQuery({
        queryKey: ['treasury', 'transactions', range],
        queryFn: () => listTransactions(range),
    });
    const { data: expensesData } = useQuery({
        queryKey: ['treasury', 'expenses', 'pending-upcoming'],
        queryFn: () => listExpenses({ status: 'pending', limit: 20 }),
    });
    const { data: fixedExpenses } = useQuery({
        queryKey: ['treasury', 'fixed-expenses'],
        queryFn: listFixedExpenses,
    });

    const stats = useMemo(() => {
        if (!accounts || !transactionsData) return null;

        const totalBalance = accounts.reduce((acc, curr) => acc + Number(curr.balance), 0);
        const txns = transactionsData.results ?? [];

        const income = txns
            .filter(t => t.direction === 'IN' && t.status === 'posted')
            .reduce((acc, curr) => acc + parseFloat(curr.amount), 0);

        const expense = txns
            .filter(t => t.direction === 'OUT' && t.status === 'posted')
            .reduce((acc, curr) => acc + parseFloat(curr.amount), 0);

        return { totalBalance, income, expense, result: income - expense };
    }, [accounts, transactionsData]);

    // Unify upcoming: pending puntuales + pending fixed expense periods this month
    const upcomingItems = useMemo(() => {
        const items: Array<{
            id: string;
            name: string;
            due_date: string;
            amount: string;
            type: 'puntual' | 'fijo';
            category_name?: string;
        }> = [];

        // Puntuales
        const expenses = expensesData?.results ?? [];
        expenses.forEach(e => {
            items.push({
                id: `exp-${e.id}`,
                name: e.name,
                due_date: e.due_date,
                amount: e.amount,
                type: 'puntual',
                category_name: e.category_name,
            });
        });

        // Fijos: iterate current_period_status
        if (fixedExpenses) {
            const currentMonth = format(today, 'yyyy-MM');
            fixedExpenses.forEach(fe => {
                const ps = fe.current_period_status;
                if (ps && ps.status === 'pending' && fe.due_day) {
                    const dueDateStr = `${currentMonth}-${String(fe.due_day).padStart(2, '0')}`;
                    items.push({
                        id: `fe-${fe.id}`,
                        name: fe.name,
                        due_date: dueDateStr,
                        amount: ps.amount,
                        type: 'fijo',
                        category_name: fe.category_name,
                    });
                }
            });
        }

        return items
            .filter(i => !isPast(new Date(i.due_date)) || isToday(new Date(i.due_date)))
            .sort((a, b) => new Date(a.due_date).getTime() - new Date(b.due_date).getTime())
            .slice(0, 8);
    }, [expensesData, fixedExpenses, today]);

    if (isAccountsLoading || isTrxLoading) return <div className="flex justify-center p-12"><Loader2 className="h-8 w-8 animate-spin text-slate-400" /></div>;
    if (!stats) return null;

    return (
        <div className="space-y-8">
            {/* Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="bg-slate-900 text-white p-6 rounded-3xl shadow-md">
                    <div className="flex items-center gap-2 mb-2 text-slate-300 text-sm font-medium">
                        <Wallet className="h-4 w-4" />
                        Saldo Total
                    </div>
                    <div className="text-3xl font-bold font-mono">
                        <Currency amount={stats.totalBalance} />
                    </div>
                    <p className="text-xs text-slate-400 mt-2">En todas las cuentas</p>
                </div>

                <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm">
                    <div className="flex items-center gap-2 mb-2 text-emerald-600 text-sm font-medium">
                        <ArrowUp className="h-4 w-4" />
                        Ingresos (Mes)
                    </div>
                    <div className="text-2xl font-bold font-mono text-emerald-700">
                        <Currency amount={stats.income} />
                    </div>
                </div>

                <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm">
                    <div className="flex items-center gap-2 mb-2 text-rose-600 text-sm font-medium">
                        <ArrowDown className="h-4 w-4" />
                        Egresos (Mes)
                    </div>
                    <div className="text-2xl font-bold font-mono text-rose-700">
                        <Currency amount={stats.expense} />
                    </div>
                </div>

                <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm">
                    <div className="flex items-center gap-2 mb-2 text-slate-600 text-sm font-medium">
                        <span>Resultado Operativo</span>
                    </div>
                    <div className={`text-2xl font-bold font-mono ${stats.result >= 0 ? 'text-slate-900' : 'text-rose-600'}`}>
                        <Currency amount={stats.result} />
                    </div>
                    <p className="text-xs text-slate-400 mt-1">Ingresos - Egresos</p>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Upcoming Expenses — puntuales + fijos unificados */}
                <div className="lg:col-span-2 space-y-4">
                    <div className="flex justify-between items-center">
                        <h3 className="text-lg font-bold text-slate-900">Próximos Vencimientos</h3>
                        <Link href="/app/gestion/finanzas/gastos" className="text-sm font-medium text-slate-600 hover:text-slate-900">Ver todos</Link>
                    </div>

                    {upcomingItems.length === 0 ? (
                        <div className="bg-slate-50 border border-dashed border-slate-300 rounded-xl p-8 text-center text-slate-500 text-sm">
                            No tenés vencimientos próximos pendientes.
                        </div>
                    ) : (
                        <div className="bg-white border border-slate-200 rounded-3xl overflow-hidden shadow-sm">
                            <table className="min-w-full divide-y divide-slate-200">
                                <thead className="bg-slate-50">
                                    <tr>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Vence</th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Detalle</th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Tipo</th>
                                        <th className="px-6 py-3 text-right text-xs font-medium text-slate-500 uppercase tracking-wider">Monto</th>
                                    </tr>
                                </thead>
                                <tbody className="bg-white divide-y divide-slate-200">
                                    {upcomingItems.map((item) => (
                                        <tr key={item.id} className="hover:bg-slate-50">
                                            <td className="px-6 py-4 whitespace-nowrap text-sm">
                                                <div className={`flex items-center font-medium ${
                                                    isToday(new Date(item.due_date)) ? 'text-amber-600' : 'text-slate-600'
                                                }`}>
                                                    <Calendar className="h-3 w-3 mr-1.5" />
                                                    {format(new Date(item.due_date), 'dd/MM/yyyy')}
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 text-sm text-slate-900">
                                                <div className="font-medium">{item.name}</div>
                                                {item.category_name && <div className="text-xs text-slate-500">{item.category_name}</div>}
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-sm">
                                                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                                                    item.type === 'fijo'
                                                        ? 'bg-blue-100 text-blue-700'
                                                        : 'bg-amber-100 text-amber-700'
                                                }`}>
                                                    {item.type === 'fijo' ? 'Fijo' : 'Puntual'}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-right font-mono font-bold text-slate-800">
                                                <Currency amount={item.amount} />
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>

                {/* Quick Actions */}
                <div className="space-y-4">
                    <h3 className="text-lg font-bold text-slate-900">Accesos Rápidos</h3>
                    <div className="grid grid-cols-1 gap-3">
                        <Link href="/app/gestion/finanzas/movimientos" className="block p-4 bg-white border border-slate-200 rounded-xl shadow-sm hover:border-slate-400 transition-colors">
                            <h4 className="font-semibold text-slate-900 mb-1">Movimientos</h4>
                            <p className="text-sm text-slate-500">Ver historial completo de ingresos y egresos.</p>
                        </Link>
                        <Link href="/app/gestion/finanzas/cuentas" className="block p-4 bg-white border border-slate-200 rounded-xl shadow-sm hover:border-slate-400 transition-colors">
                            <h4 className="font-semibold text-slate-900 mb-1">Cuentas</h4>
                            <p className="text-sm text-slate-500">Administrar saldos y conciliaciones.</p>
                        </Link>
                        <Link href="/app/gestion/finanzas/sueldos" className="block p-4 bg-white border border-slate-200 rounded-xl shadow-sm hover:border-slate-400 transition-colors">
                            <h4 className="font-semibold text-slate-900 mb-1">Sueldos</h4>
                            <p className="text-sm text-slate-500">Gestionar empleados y pagos.</p>
                        </Link>
                        <Link href="/app/gestion/finanzas/reportes" className="block p-4 bg-white border border-slate-200 rounded-xl shadow-sm hover:border-slate-400 transition-colors">
                            <h4 className="font-semibold text-slate-900 mb-1">Reportes</h4>
                            <p className="text-sm text-slate-500">Flujo de caja de los últimos 12 meses.</p>
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    );
}
