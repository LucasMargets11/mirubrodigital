'use client';

import { Pie, PieChart, ResponsiveContainer, Tooltip, TooltipProps, Cell } from 'recharts';

import type { PaymentBreakdownRow } from '@/features/reports/types';

import { formatARS, humanizePaymentMethod, toNumber } from '../utils/format';

export type PaymentsDonutChartProps = {
    data: PaymentBreakdownRow[];
    topN?: number;
};

type ChartDatum = {
    method: string;
    label: string;
    value: number;
    payments_count: number;
    percent: number;
    color: string;
};

const METHOD_COLORS: Record<string, string> = {
    CASH: '#0f766e',
    CARD: '#7c3aed',
    DEBIT: '#14b8a6',
    CREDIT: '#a21caf',
    TRANSFER: '#2563eb',
    WIRE: '#2563eb',
    MP: '#f97316',
    MERCADO_PAGO: '#f97316',
    QR: '#be123c',
    OTHER: '#6b7280',
    OTHERS: '#6b7280',
};

const FALLBACK_COLORS = ['#312e81', '#7c3aed', '#0f766e', '#be123c', '#fb923c', '#0ea5e9'];

export function PaymentsDonutChart({ data, topN = 5 }: PaymentsDonutChartProps) {
    const prepared = prepareData(data, topN);

    if (!prepared.length) {
        return null;
    }

    return (
        <div className="flex h-full w-full min-h-0 flex-col gap-6 md:flex-row md:items-center">
            <div className="relative flex-none min-h-[16rem] w-full md:flex-1 md:h-full md:min-h-0">
                <div className="h-64 md:h-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                            <Pie
                                data={prepared}
                                dataKey="value"
                                nameKey="label"
                                innerRadius="60%"
                                outerRadius="85%"
                                cx="50%"
                                cy="50%"
                                paddingAngle={2}
                                stroke="white"
                                strokeWidth={2}
                            >
                                {prepared.map((entry) => (
                                    <Cell key={entry.method} fill={entry.color} />
                                ))}
                            </Pie>
                            <Tooltip content={<PaymentsTooltip />} />
                        </PieChart>
                    </ResponsiveContainer>
                </div>
            </div>
            <div className="flex-1 min-h-0 space-y-3 overflow-y-auto md:flex-none md:w-56 md:shrink-0 md:max-h-full">
                {prepared.map((item) => (
                    <div key={item.method} className="flex items-center justify-between rounded-2xl border border-slate-100 bg-slate-50/60 p-3">
                        <div className="flex items-center gap-3">
                            <span className="h-2 w-8 rounded-full" style={{ backgroundColor: item.color }} />
                            <div>
                                <p className="font-semibold text-slate-900">{item.label}</p>
                                <p className="text-xs text-slate-500">{item.payments_count} pagos</p>
                            </div>
                        </div>
                        <div className="text-right text-sm">
                            <p className="font-semibold text-slate-900">{item.percent.toFixed(1)}%</p>
                            <p className="text-xs text-slate-500">{formatARS(item.value)}</p>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

function PaymentsTooltip({ active, payload }: TooltipProps<number, string>) {
    if (!active || !payload?.length) {
        return null;
    }
    const entry = payload[0].payload as ChartDatum;
    return (
        <div className="rounded-2xl border border-slate-200 bg-white/95 p-3 text-sm text-slate-600 shadow-lg">
            <p className="font-semibold text-slate-900">{entry.label}</p>
            <p>Monto: {formatARS(entry.value)}</p>
            <p>Pagos: {entry.payments_count}</p>
            <p>Participación: {entry.percent.toFixed(1)}%</p>
        </div>
    );
}

function prepareData(data: PaymentBreakdownRow[], topN: number): ChartDatum[] {
    if (!data?.length || topN <= 0) {
        return [];
    }

    const sorted = [...data].sort((a, b) => toNumber(b.amount_total) - toNumber(a.amount_total));
    const head = sorted.slice(0, topN);
    const tail = sorted.slice(topN);

    if (tail.length) {
        const amount = tail.reduce((sum, row) => sum + toNumber(row.amount_total), 0);
        const payments = tail.reduce((sum, row) => sum + (row.payments_count ?? 0), 0);
        const sales = tail.reduce((sum, row) => sum + (row.sales_count ?? 0), 0);
        head.push({
            method: 'OTHERS',
            method_label: 'Otros',
            amount_total: amount.toFixed(2),
            payments_count: payments,
            sales_count: sales,
        });
    }

    const total = head.reduce((sum, row) => sum + toNumber(row.amount_total), 0);
    if (total <= 0) {
        return [];
    }

    return head.map((row, index) => {
        const normalizedMethod = (row.method ?? `METHOD_${index}`).trim().toUpperCase();
        const value = toNumber(row.amount_total);
        return {
            method: normalizedMethod,
            label: normalizedMethod === 'OTHERS' ? 'Otros' : row.method_label ?? humanizePaymentMethod(row.method),
            value,
            payments_count: row.payments_count ?? 0,
            percent: (value / total) * 100,
            color: getColorForMethod(normalizedMethod),
        };
    });
}

function getColorForMethod(method: string) {
    if (METHOD_COLORS[method]) {
        return METHOD_COLORS[method];
    }
    const hash = method.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    return FALLBACK_COLORS[hash % FALLBACK_COLORS.length];
}
