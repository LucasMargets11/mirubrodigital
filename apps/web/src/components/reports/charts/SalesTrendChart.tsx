'use client';

import { Area, Bar, CartesianGrid, ComposedChart, ResponsiveContainer, Tooltip, TooltipProps, XAxis, YAxis } from 'recharts';

import { formatARS, formatARSCompact, formatDateLong, formatDateShort, compactNumber, toNumber } from '../utils/format';
import type { TrendPoint } from '../utils/fillMissingPeriods';

export type SalesTrendChartProps = {
    data: TrendPoint[];
};

type ChartDatum = TrendPoint & {
    grossSalesValue: number;
    avgTicketValue: number;
    periodShort: string;
    periodLong: string;
};

export function SalesTrendChart({ data }: SalesTrendChartProps) {
    const chartData: ChartDatum[] = data.map((point) => ({
        ...point,
        grossSalesValue: toNumber(point.gross_sales),
        avgTicketValue: toNumber(point.avg_ticket),
        periodShort: formatDateShort(point.period),
        periodLong: formatDateLong(point.period),
    }));

    return (
        <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <defs>
                    <linearGradient id="salesTrend" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#312e81" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="#312e81" stopOpacity={0.05} />
                    </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis
                    dataKey="periodShort"
                    stroke="#94a3b8"
                    tickLine={false}
                    axisLine={false}
                />
                <YAxis
                    yAxisId="left"
                    stroke="#94a3b8"
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(value) => formatARSCompact(value)}
                />
                <YAxis
                    yAxisId="right"
                    orientation="right"
                    stroke="#94a3b8"
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(value) => compactNumber(value)}
                />
                <Tooltip content={<SalesTrendTooltip />} />
                <Bar
                    yAxisId="right"
                    dataKey="sales_count"
                    name="Cantidad de ventas"
                    barSize={18}
                    fill="#c084fc"
                    radius={[4, 4, 0, 0]}
                />
                <Area
                    yAxisId="left"
                    type="monotone"
                    dataKey="grossSalesValue"
                    name="Ventas brutas"
                    stroke="#312e81"
                    strokeWidth={2}
                    fill="url(#salesTrend)"
                />
            </ComposedChart>
        </ResponsiveContainer>
    );
}

function SalesTrendTooltip({ active, payload }: TooltipProps<number, string>) {
    if (!active || !payload?.length) {
        return null;
    }
    const point = payload[0].payload as ChartDatum;
    return (
        <div className="rounded-2xl border border-slate-200 bg-white/95 p-3 text-sm text-slate-600 shadow-lg">
            <p className="font-semibold text-slate-900">{point.periodLong}</p>
            <p>Ventas brutas: {formatARS(point.grossSalesValue)}</p>
            <p>Cantidad de ventas: {point.sales_count}</p>
            <p>Ticket promedio: {formatARS(point.avgTicketValue)}</p>
        </div>
    );
}
