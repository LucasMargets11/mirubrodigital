"use client";

import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import { format, startOfMonth, endOfMonth, isPast, isToday } from 'date-fns';
import { ArrowUp, ArrowDown, Wallet, Calendar } from 'lucide-react';
import { es } from 'date-fns/locale';
import Link from 'next/link';

import { listAccounts, listTransactions, listExpenses } from '@/lib/api/treasury';
import { Currency } from '../components/currency';
import { Button } from '@/components/ui/button';
import { Loader2 } from 'lucide-react';

export function DashboardClient({ canManage }: { canManage: boolean }) {
    const today = new Date();
    const range = {
        date_from: format(startOfMonth(today), 'yyyy-MM-dd'),
        date_to: format(endOfMonth(today), 'yyyy-MM-dd'),
    };

    const { data: accounts, isLoading: isAccountsLoading } = useQuery({ queryKey: ['treasury', 'accounts'], queryFn: listAccounts });
    const { data: transactions, isLoading: isTrxLoading } = useQuery({ queryKey: ['treasury', 'transactions', range], queryFn: () => listTransactions(range) });
    const { data: expenses, isLoading: isExpensesLoading } = useQuery({ queryKey: ['treasury', 'expenses'], queryFn: listExpenses });

    const stats = useMemo(() => {
        if (!accounts || !transactions) return null;

        const totalBalance = accounts.reduce((acc, curr) => acc + curr.balance, 0);
        
        const income = transactions
            .filter(t => t.direction === 'IN')
            .reduce((acc, curr) => acc + parseFloat(curr.amount), 0);
            
        const expense = transactions
            .filter(t => t.direction === 'OUT')
            .reduce((acc, curr) => acc + parseFloat(curr.amount), 0);

        return {
            totalBalance,
            income,
            expense,
            result: income - expense
        };
    }, [accounts, transactions]);

    const upcomingExpenses = useMemo(() => {
        if (!expenses) return [];
        return expenses
            .filter(e => e.status === 'pending')
            .sort((a, b) => new Date(a.due_date).getTime() - new Date(b.due_date).getTime())
            .slice(0, 5); // Take first 5
    }, [expenses]);

    if (isAccountsLoading || isTrxLoading || isExpensesLoading) return <div className="flex justify-center p-12"><Loader2 className="h-8 w-8 animate-spin text-slate-400" /></div>;

    if (!stats) return null; // Should not happen after loading

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
                {/* Upcoming Expenses */}
                <div className="lg:col-span-2 space-y-4">
                    <div className="flex justify-between items-center">
                        <h3 className="text-lg font-bold text-slate-900">Próximos Vencimientos</h3>
                        <Link href="/app/gestion/finanzas/gastos" className="text-sm font-medium text-slate-600 hover:text-slate-900">Ver todos</Link>
                    </div>
                    
                    {upcomingExpenses.length === 0 ? (
                        <div className="bg-slate-50 border border-dashed border-slate-300 rounded-xl p-8 text-center text-slate-500 text-sm">
                            No tenés gastos pendientes.
                        </div>
                    ) : (
                         <div className="bg-white border border-slate-200 rounded-3xl overflow-hidden shadow-sm">
                            <table className="min-w-full divide-y divide-slate-200">
                                <thead className="bg-slate-50">
                                    <tr>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Vence</th>
                                        <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Detalle</th>
                                        <th className="px-6 py-3 text-right text-xs font-medium text-slate-500 uppercase tracking-wider">Monto</th>
                                        <th className="px-6 py-3 text-right text-xs font-medium text-slate-500 uppercase tracking-wider"></th>
                                    </tr>
                                </thead>
                                <tbody className="bg-white divide-y divide-slate-200">
                                    {upcomingExpenses.map((expense) => (
                                        <tr key={expense.id} className="hover:bg-slate-50">
                                            <td className="px-6 py-4 whitespace-nowrap text-sm">
                                                <div className={`flex items-center font-medium ${
                                                    isPast(new Date(expense.due_date)) && !isToday(new Date(expense.due_date)) ? "text-rose-600" :
                                                    isToday(new Date(expense.due_date)) ? "text-amber-600" : "text-slate-600"
                                                }`}>
                                                    <Calendar className="h-3 w-3 mr-1.5" />
                                                    {format(new Date(expense.due_date), 'dd/MM/yyyy')}
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 text-sm text-slate-900">
                                                <div className="font-medium">{expense.name}</div>
                                                <div className="text-xs text-slate-500">{expense.category_name}</div>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-right font-mono font-bold text-slate-800">
                                                <Currency amount={expense.amount} />
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                                <Link href="/app/gestion/finanzas/gastos" className="text-slate-400 hover:text-slate-900">Ir a pagar</Link>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>

                {/* Quick Actions or Summary */}
                <div className="space-y-4">
                     <h3 className="text-lg font-bold text-slate-900">Accesos Rápidos</h3>
                     <div className="grid grid-cols-1 gap-4">
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
                     </div>
                </div>
            </div>
        </div>
    );
}
