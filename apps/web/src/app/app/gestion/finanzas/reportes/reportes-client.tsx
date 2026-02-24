"use client";

import { useQuery } from '@tanstack/react-query';
import { BarChart3, Loader2, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { getMonthlyReport, MonthlyReport } from '@/lib/api/treasury';
import { Currency } from '../components/currency';
import { EmptyState } from '../components/empty-state';

function toNum(v: number | string) {
    return typeof v === 'string' ? parseFloat(v) : v;
}

export function ReportesClient() {
    const { data: report, isLoading } = useQuery({
        queryKey: ['treasury', 'monthly-report'],
        queryFn: getMonthlyReport,
    });

    if (isLoading) {
        return <div className="flex justify-center p-12"><Loader2 className="h-8 w-8 animate-spin text-slate-400" /></div>;
    }

    if (!report || report.length === 0) {
        return (
            <EmptyState
                title="Sin datos de reportes"
                description="Aún no hay movimientos registrados para generar reportes mensuales."
            />
        );
    }

    const maxIncome = Math.max(...report.map(m => toNum(m.income)), 1);
    const maxExpense = Math.max(...report.map(m => toNum(m.expense)), 1);
    const maxBar = Math.max(maxIncome, maxExpense);

    const totalIncome = report.reduce((s, m) => s + toNum(m.income), 0);
    const totalExpense = report.reduce((s, m) => s + toNum(m.expense), 0);
    const totalResult = totalIncome - totalExpense;

    return (
        <div className="space-y-6">
            <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-slate-100">
                    <BarChart3 className="h-6 w-6 text-slate-700" />
                </div>
                <div>
                    <h2 className="text-lg font-semibold text-slate-900">Reporte Mensual</h2>
                    <p className="text-sm text-slate-500">Últimos 12 meses — ingresos, egresos y resultado</p>
                </div>
            </div>

            {/* Summary cards */}
            <div className="grid grid-cols-3 gap-4">
                <SummaryCard label="Total Ingresos" value={totalIncome} colorClass="text-emerald-600" bgClass="bg-emerald-50 border-emerald-200" icon={<TrendingUp className="h-5 w-5 text-emerald-500" />} />
                <SummaryCard label="Total Egresos" value={totalExpense} colorClass="text-rose-600" bgClass="bg-rose-50 border-rose-200" icon={<TrendingDown className="h-5 w-5 text-rose-500" />} />
                <SummaryCard label="Resultado Neto" value={totalResult} colorClass={totalResult >= 0 ? 'text-emerald-700' : 'text-rose-700'} bgClass={totalResult >= 0 ? 'bg-emerald-50 border-emerald-200' : 'bg-rose-50 border-rose-200'} icon={<Minus className="h-5 w-5 text-slate-500" />} />
            </div>

            {/* Bar visualization */}
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm overflow-x-auto">
                <div className="flex items-end gap-3 min-w-[600px]" style={{ height: 180 }}>
                    {report.map((m) => {
                        const inc = toNum(m.income);
                        const exp = toNum(m.expense);
                        return (
                            <div key={`${m.year}-${m.month}`} className="flex-1 flex flex-col items-center gap-1 group">
                                <div className="flex items-end gap-0.5 w-full justify-center" style={{ height: 140 }}>
                                    <div
                                        className="w-4 rounded-t-sm bg-emerald-400 group-hover:bg-emerald-500 transition-all"
                                        style={{ height: `${Math.round((inc / maxBar) * 140)}px` }}
                                        title={`Ingresos: $${inc.toFixed(2)}`}
                                    />
                                    <div
                                        className="w-4 rounded-t-sm bg-rose-400 group-hover:bg-rose-500 transition-all"
                                        style={{ height: `${Math.round((exp / maxBar) * 140)}px` }}
                                        title={`Egresos: $${exp.toFixed(2)}`}
                                    />
                                </div>
                                <span className="text-[10px] text-slate-500 text-center leading-tight">{m.label}</span>
                            </div>
                        );
                    })}
                </div>
                <div className="flex gap-4 mt-3 justify-center">
                    <span className="flex items-center gap-1.5 text-xs text-slate-600"><span className="w-3 h-3 rounded-sm bg-emerald-400 inline-block" />Ingresos</span>
                    <span className="flex items-center gap-1.5 text-xs text-slate-600"><span className="w-3 h-3 rounded-sm bg-rose-400 inline-block" />Egresos</span>
                </div>
            </div>

            {/* Table */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                <table className="w-full text-sm">
                    <thead className="bg-slate-50 border-b border-slate-200">
                        <tr>
                            <th className="text-left px-5 py-3 font-medium text-slate-600">Mes</th>
                            <th className="text-right px-5 py-3 font-medium text-slate-600">Ingresos</th>
                            <th className="text-right px-5 py-3 font-medium text-slate-600">Egresos</th>
                            <th className="text-right px-5 py-3 font-medium text-slate-600">Resultado</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                        {[...report].reverse().map((m) => {
                            const inc = toNum(m.income);
                            const exp = toNum(m.expense);
                            const res = inc - exp;
                            return (
                                <tr key={`${m.year}-${m.month}`} className="hover:bg-slate-50">
                                    <td className="px-5 py-3 font-medium text-slate-800">{m.label}</td>
                                    <td className="px-5 py-3 text-right text-emerald-600 font-mono">
                                        +<Currency amount={String(inc)} />
                                    </td>
                                    <td className="px-5 py-3 text-right text-rose-600 font-mono">
                                        -<Currency amount={String(exp)} />
                                    </td>
                                    <td className={`px-5 py-3 text-right font-mono font-semibold ${res >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
                                        {res >= 0 ? '+' : ''}<Currency amount={String(res)} />
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                    <tfoot className="bg-slate-50 border-t-2 border-slate-200">
                        <tr>
                            <td className="px-5 py-3 font-semibold text-slate-800">Total</td>
                            <td className="px-5 py-3 text-right text-emerald-700 font-mono font-semibold">+<Currency amount={String(totalIncome)} /></td>
                            <td className="px-5 py-3 text-right text-rose-700 font-mono font-semibold">-<Currency amount={String(totalExpense)} /></td>
                            <td className={`px-5 py-3 text-right font-mono font-bold ${totalResult >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
                                {totalResult >= 0 ? '+' : ''}<Currency amount={String(totalResult)} />
                            </td>
                        </tr>
                    </tfoot>
                </table>
            </div>
        </div>
    );
}

function SummaryCard({
    label, value, colorClass, bgClass, icon
}: {
    label: string;
    value: number;
    colorClass: string;
    bgClass: string;
    icon: React.ReactNode;
}) {
    return (
        <div className={`rounded-2xl border p-4 ${bgClass}`}>
            <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-slate-600">{label}</span>
                {icon}
            </div>
            <div className={`text-xl font-bold font-mono ${colorClass}`}>
                <Currency amount={String(value)} />
            </div>
        </div>
    );
}
