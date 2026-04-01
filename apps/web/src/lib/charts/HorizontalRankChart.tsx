'use client';

import { useMemo } from 'react';
import type { EChartsCoreOption } from 'echarts/core';
import { EChart } from './EChart';
import {
    TOOLTIP_BASE_STYLE,
    COLOR_AXIS_LABEL,
    CATEGORICAL_PALETTE,
} from './theme';

/* ── Public types ─────────────────────────────────────────── */

export type RankItem = {
    name: string;
    value: number;
};

export type HorizontalRankChartProps = {
    items: RankItem[];
    /** Format the value as the bar label (right of each bar) and in the default tooltip */
    formatLabel?: (v: number) => string;
    /** Override the tooltip HTML. Receives (name, value, 0-based index in the original items array). */
    formatTooltip?: (name: string, value: number, index: number) => string;
    /** Bar colour. Default: CATEGORICAL_PALETTE[0] (indigo-900) */
    color?: string;
    height?: number | string;
    className?: string;
};

/* ── Option builder (exported for testing) ────────────────── */

export function buildHorizontalRankOption(
    items: RankItem[],
    opts?: {
        formatLabel?: (v: number) => string;
        formatTooltip?: (name: string, value: number, index: number) => string;
        color?: string;
    },
): EChartsCoreOption {
    const fmtLabel = opts?.formatLabel ?? String;
    const fmtTooltip = opts?.formatTooltip;
    const barColor = opts?.color ?? CATEGORICAL_PALETTE[0];

    // Reverse so #1 appears at the top (ECharts yAxis renders bottom→up)
    const reversed = [...items].reverse();
    const categories = reversed.map((i) => i.name);
    const values = reversed.map((i) => i.value);

    return {
        tooltip: {
            ...TOOLTIP_BASE_STYLE,
            trigger: 'item',
            formatter(params: any) {
                const p = Array.isArray(params) ? params[0] : params;
                const originalIdx = items.length - 1 - p.dataIndex;
                if (fmtTooltip) return fmtTooltip(p.name, p.value, originalIdx);
                return `<div style="font-weight:600;margin-bottom:4px">${p.name}</div>
                    <div style="font-family:ui-monospace,monospace;font-weight:600">${fmtLabel(p.value)}</div>`;
            },
        },
        grid: {
            left: 8,
            right: 16,
            top: 4,
            bottom: 4,
            containLabel: true,
        },
        xAxis: {
            type: 'value',
            axisLabel: { show: false },
            splitLine: { show: false },
            axisLine: { show: false },
            axisTick: { show: false },
        },
        yAxis: {
            type: 'category',
            data: categories,
            axisLabel: {
                color: COLOR_AXIS_LABEL,
                fontSize: 12,
                width: 120,
                overflow: 'truncate',
            },
            axisLine: { show: false },
            axisTick: { show: false },
        },
        series: [
            {
                type: 'bar',
                data: values,
                itemStyle: {
                    color: barColor,
                    borderRadius: [0, 4, 4, 0],
                },
                barWidth: 16,
                label: {
                    show: true,
                    position: 'right',
                    color: '#334155', // slate-700
                    fontSize: 12,
                    fontFamily: 'ui-monospace, monospace',
                    formatter: (p: any) => fmtLabel(p.value),
                },
            },
        ],
    };
}

/* ── Component ────────────────────────────────────────────── */

export function HorizontalRankChart({
    items,
    formatLabel,
    formatTooltip,
    color,
    height,
    className,
}: HorizontalRankChartProps) {
    const chartHeight = height ?? items.length * 36 + 16;

    const option = useMemo(
        () => buildHorizontalRankOption(items, { formatLabel, formatTooltip, color }),
        // Functions are stable by convention; only data triggers rebuilds
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [items, color],
    );

    return <EChart option={option} height={chartHeight} className={className} />;
}
