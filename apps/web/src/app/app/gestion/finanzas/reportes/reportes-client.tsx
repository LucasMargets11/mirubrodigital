"use client";

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { BarChart3, Loader2, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { EChartsCoreOption } from 'echarts/core';
import { getMonthlyReport, MonthlyReport } from '@/lib/api/treasury';
import { EChart } from '@/lib/charts';
import {
    COLOR_AXIS_LABEL,
    COLOR_GRID_LINE,
    TOOLTIP_BASE_STYLE,
} from '@/lib/charts/theme';
import { Currency } from '../components/currency';
import { EmptyState } from '../components/empty-state';

function toNum(v: number | string) {
    return typeof v === 'string' ? parseFloat(v) : v;
}

/* ── ARS formatter shared between tooltip and yAxis ── */
const fmtARS = new Intl.NumberFormat('es-AR', {
    style: 'currency',
    currency: 'ARS',
    notation: 'compact',
    maximumFractionDigits: 1,
});

const fmtARSFull = new Intl.NumberFormat('es-AR', {
    style: 'currency',
    currency: 'ARS',
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
});

/* ── Colour tokens matching the existing emerald/rose palette ── */
const COLOR_INCOME = '#10b981';   // emerald-500
const COLOR_EXPENSE = '#f43f5e';  // rose-500

/**
 * Pure function: builds the ECharts option for the monthly income/expense
 * grouped bar chart.  Exported for testing.
 */
export function buildMonthlyReportOption(data: MonthlyReport[]): EChartsCoreOption {
    const categories = data.map((m) => m.label);
    const incomeData = data.map((m) => toNum(m.income));
    const expenseData = data.map((m) => toNum(m.expense));

    return {
        tooltip: {
            ...TOOLTIP_BASE_STYLE,
            trigger: 'axis',
            axisPointer: {
                type: 'shadow',
                animation: false,
                shadowStyle: { color: 'rgba(0,0,0,0.03)' },
            },
            formatter(params: any) {
                const items = Array.isArray(params) ? params : [params];
                const month = items[0]?.axisValueLabel ?? '';
                const dot = (c: string) => `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${c};margin-right:6px;vertical-align:middle"></span>`;
                let html = `<div style="font-weight:600;color:#0f172a;margin-bottom:8px;font-size:13px">${month}</div>`;
                for (const p of items) {
                    html += `<div style="display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:3px">
                        <span>${dot(p.color)}${p.seriesName}</span>
                        <span style="font-weight:600;font-family:ui-monospace,monospace">${fmtARSFull.format(p.value)}</span>
                    </div>`;
                }
                const inc = items.find((i: any) => i.seriesName === 'Ingresos')?.value ?? 0;
                const exp = items.find((i: any) => i.seriesName === 'Egresos')?.value ?? 0;
                const res = inc - exp;
                const resColor = res >= 0 ? '#059669' : '#e11d48';
                html += `<div style="margin-top:6px;padding-top:6px;border-top:1px solid #e2e8f0;display:flex;align-items:center;justify-content:space-between;gap:16px">
                    <span style="font-weight:600">Resultado</span>
                    <span style="font-weight:700;color:${resColor};font-family:ui-monospace,monospace">${fmtARSFull.format(res)}</span>
                </div>`;
                return html;
            },
        },
        legend: {
            show: true,
            bottom: 0,
            icon: 'circle',
            itemWidth: 8,
            itemHeight: 8,
            itemGap: 24,
            textStyle: { color: '#64748b', fontSize: 12 },
        },
        grid: {
            left: 8,
            right: 8,
            top: 16,
            bottom: 40,
            containLabel: true,
        },
        xAxis: {
            type: 'category',
            data: categories,
            axisLabel: { color: COLOR_AXIS_LABEL, fontSize: 11, margin: 12 },
            axisLine: { show: false },
            axisTick: { show: false },
        },
        yAxis: {
            type: 'value',
            axisLabel: {
                color: COLOR_AXIS_LABEL,
                fontSize: 11,
                formatter: (v: number) => fmtARS.format(v),
            },
            axisLine: { show: false },
            axisTick: { show: false },
            splitLine: { lineStyle: { color: COLOR_GRID_LINE, type: 'dashed', opacity: 0.7 } },
            splitNumber: 4,
        },
        series: [
            {
                name: 'Ingresos',
                type: 'bar',
                data: incomeData,
                barWidth: 14,
                barGap: '30%',
                itemStyle: { color: COLOR_INCOME, borderRadius: [4, 4, 0, 0] },
                emphasis: { itemStyle: { color: '#059669' } },
            },
            {
                name: 'Egresos',
                type: 'bar',
                data: expenseData,
                barWidth: 14,
                itemStyle: { color: COLOR_EXPENSE, borderRadius: [4, 4, 0, 0] },
                emphasis: { itemStyle: { color: '#e11d48' } },
            },
        ],
    };
}

export function ReportesClient() {
    const { data: report, isLoading } = useQuery({
        queryKey: ['treasury', 'monthly-report'],
        queryFn: getMonthlyReport,
    });

    const chartOption = useMemo(() => buildMonthlyReportOption(report ?? []), [report]);

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

            {/* Bar chart */}
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
                <EChart option={chartOption} height={220} />
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
