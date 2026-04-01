'use client';

import { useMemo } from 'react';
import type { EChartsCoreOption } from 'echarts/core';

import { EChart } from '@/lib/charts';
import {
    COLOR_PRIMARY,
    COLOR_SECONDARY,
    COLOR_AXIS_LABEL,
    COLOR_GRID_LINE,
    TOOLTIP_BASE_STYLE,
    primaryAreaGradient,
} from '@/lib/charts/theme';
import { formatARS, formatARSCompact, formatDateLong, formatDateShort, compactNumber, toNumber } from '../utils/format';
import type { TrendPoint } from '../utils/fillMissingPeriods';

export type SalesTrendChartProps = {
    data: TrendPoint[];
};

export function SalesTrendChart({ data }: SalesTrendChartProps) {
    const option = useMemo(() => buildOption(data), [data]);
    return <EChart option={option} height="100%" />;
}

// ── Option builder (pure, testable) ─────────────────────────

export function buildSalesTrendOption(data: TrendPoint[]): EChartsCoreOption {
    return buildOption(data);
}

function buildOption(data: TrendPoint[]): EChartsCoreOption {
    const categories: string[] = [];
    const grossSales: number[] = [];
    const salesCount: number[] = [];
    const avgTickets: number[] = [];
    const periodLongs: string[] = [];

    for (const point of data) {
        categories.push(formatDateShort(point.period));
        grossSales.push(toNumber(point.gross_sales));
        salesCount.push(point.sales_count);
        avgTickets.push(toNumber(point.avg_ticket));
        periodLongs.push(formatDateLong(point.period));
    }

    return {
        grid: { top: 24, right: 56, bottom: 32, left: 4, containLabel: true },
        tooltip: {
            ...TOOLTIP_BASE_STYLE,
            trigger: 'axis',
            axisPointer: {
                type: 'cross',
                animation: false,
                label: { show: false },
                crossStyle: { color: 'transparent' },
                lineStyle: { color: COLOR_GRID_LINE, type: 'dashed' },
            },
            formatter(params: unknown) {
                const items = params as Array<{ dataIndex: number; color: string; seriesName: string; value: number }>;
                if (!items?.length) return '';
                const idx = items[0].dataIndex;
                const dot = (c: string) => `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${c};margin-right:6px;vertical-align:middle"></span>`;
                return [
                    `<div style="font-weight:600;color:#0f172a;margin-bottom:8px;font-size:13px">${periodLongs[idx]}</div>`,
                    `<div style="display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:3px">`,
                    `  <span>${dot(COLOR_PRIMARY)}Ventas brutas</span>`,
                    `  <span style="font-weight:600;font-family:ui-monospace,monospace">${formatARS(grossSales[idx])}</span>`,
                    `</div>`,
                    `<div style="display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:3px">`,
                    `  <span>${dot('#c4b5fd')}Cantidad</span>`,
                    `  <span style="font-weight:600;font-family:ui-monospace,monospace">${salesCount[idx]}</span>`,
                    `</div>`,
                    `<div style="display:flex;align-items:center;justify-content:space-between;gap:16px">`,
                    `  <span style="color:#94a3b8">Ticket promedio</span>`,
                    `  <span style="font-weight:500;font-family:ui-monospace,monospace;color:#64748b">${formatARS(avgTickets[idx])}</span>`,
                    `</div>`,
                ].join('');
            },
        },
        xAxis: {
            type: 'category',
            data: categories,
            axisLabel: { color: COLOR_AXIS_LABEL, fontSize: 11, margin: 12 },
            axisTick: { show: false },
            axisLine: { show: false },
            boundaryGap: true,
        },
        yAxis: [
            {
                type: 'value',
                position: 'left',
                axisLabel: {
                    color: COLOR_AXIS_LABEL,
                    fontSize: 11,
                    formatter: (v: number) => formatARSCompact(v),
                },
                axisTick: { show: false },
                axisLine: { show: false },
                splitLine: { lineStyle: { color: COLOR_GRID_LINE, type: 'dashed', opacity: 0.7 } },
                splitNumber: 4,
            },
            {
                type: 'value',
                position: 'right',
                axisLabel: {
                    color: COLOR_AXIS_LABEL,
                    fontSize: 11,
                    formatter: (v: number) => compactNumber(v),
                },
                axisTick: { show: false },
                axisLine: { show: false },
                splitLine: { show: false },
                splitNumber: 4,
            },
        ],
        series: [
            {
                name: 'Cantidad de ventas',
                type: 'bar',
                yAxisIndex: 1,
                data: salesCount,
                barWidth: 12,
                itemStyle: {
                    color: 'rgba(196,181,253,0.35)', // violet-300 @ 35%
                    borderRadius: [3, 3, 0, 0],
                },
                emphasis: {
                    itemStyle: { color: 'rgba(196,181,253,0.55)' },
                },
                z: 1,
                silent: false,
            },
            {
                name: 'Ventas brutas',
                type: 'line',
                yAxisIndex: 0,
                data: grossSales,
                smooth: 0.35,
                symbol: 'circle',
                symbolSize: 6,
                showSymbol: false,
                lineStyle: { width: 2.5, color: COLOR_PRIMARY },
                itemStyle: { color: COLOR_PRIMARY, borderWidth: 2, borderColor: '#fff' },
                emphasis: {
                    scale: true,
                    itemStyle: { shadowBlur: 8, shadowColor: 'rgba(49,46,129,0.3)' },
                },
                areaStyle: { color: primaryAreaGradient() },
                z: 2,
            },
        ],
    } satisfies EChartsCoreOption;
}
