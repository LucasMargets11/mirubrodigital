'use client';

import { useMemo } from 'react';
import type { EChartsCoreOption } from 'echarts/core';

import { EChart } from '@/lib/charts';
import { TOOLTIP_BASE_STYLE, CATEGORICAL_PALETTE } from '@/lib/charts/theme';
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

const FALLBACK_COLORS = CATEGORICAL_PALETTE.slice(0, 6);

export function PaymentsDonutChart({ data, topN = 5 }: PaymentsDonutChartProps) {
    const prepared = prepareData(data, topN);

    if (!prepared.length) {
        return null;
    }

    const option = useMemo(() => buildDonutOption(prepared), [prepared]);

    return (
        <div className="flex h-full w-full min-h-0 flex-col gap-6 md:flex-row md:items-center">
            <div className="relative flex-none min-h-[16rem] w-full md:flex-1 md:h-full md:min-h-0">
                <div className="h-64 md:h-full">
                    <EChart option={option} height="100%" />
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

// ── Option builder (pure, testable) ─────────────────────────

export function buildDonutOption(prepared: ChartDatum[]): EChartsCoreOption {
    return {
        tooltip: {
            ...TOOLTIP_BASE_STYLE,
            trigger: 'item',
            formatter(params: unknown) {
                const p = params as { data: { label: string; value: number; payments_count: number; percent: number } };
                const d = p.data;
                return [
                    `<p style="font-weight:600;color:#0f172a;margin:0 0 4px">${d.label}</p>`,
                    `<p style="margin:0">Monto: ${formatARS(d.value)}</p>`,
                    `<p style="margin:0">Pagos: ${d.payments_count}</p>`,
                    `<p style="margin:0">Participación: ${d.percent.toFixed(1)}%</p>`,
                ].join('');
            },
        },
        series: [
            {
                type: 'pie',
                radius: ['60%', '85%'],
                center: ['50%', '50%'],
                padAngle: 2,
                itemStyle: {
                    borderColor: '#ffffff',
                    borderWidth: 2,
                },
                label: { show: false },
                data: prepared.map((item) => ({
                    name: item.label,
                    value: item.value,
                    // extra fields for tooltip formatter
                    label: item.label,
                    payments_count: item.payments_count,
                    percent: item.percent,
                    itemStyle: { color: item.color },
                })),
            },
        ],
    } satisfies EChartsCoreOption;
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
