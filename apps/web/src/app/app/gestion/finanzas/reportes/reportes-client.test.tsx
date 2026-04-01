import { describe, it, expect } from 'vitest';
import { buildMonthlyReportOption } from './reportes-client';
import type { MonthlyReport } from '@/lib/api/treasury';

const SAMPLE: MonthlyReport[] = [
    { year: 2026, month: 1, label: 'Ene 2026', income: 500000, expense: 320000, result: 180000 },
    { year: 2026, month: 2, label: 'Feb 2026', income: 420000, expense: 380000, result: 40000 },
    { year: 2026, month: 3, label: 'Mar 2026', income: 610000, expense: 250000, result: 360000 },
];

describe('buildMonthlyReportOption', () => {
    it('returns 2 bar series (Ingresos + Egresos)', () => {
        const opt = buildMonthlyReportOption(SAMPLE);
        const series = opt.series as any[];
        expect(series).toHaveLength(2);
        expect(series[0].name).toBe('Ingresos');
        expect(series[1].name).toBe('Egresos');
        expect(series[0].type).toBe('bar');
        expect(series[1].type).toBe('bar');
    });

    it('maps categories from data labels', () => {
        const opt = buildMonthlyReportOption(SAMPLE);
        const xAxis = opt.xAxis as any;
        expect(xAxis.data).toEqual(['Ene 2026', 'Feb 2026', 'Mar 2026']);
    });

    it('maps income data to first series', () => {
        const opt = buildMonthlyReportOption(SAMPLE);
        const series = opt.series as any[];
        expect(series[0].data).toEqual([500000, 420000, 610000]);
    });

    it('maps expense data to second series', () => {
        const opt = buildMonthlyReportOption(SAMPLE);
        const series = opt.series as any[];
        expect(series[1].data).toEqual([320000, 380000, 250000]);
    });

    it('uses emerald for income and rose for expense', () => {
        const opt = buildMonthlyReportOption(SAMPLE);
        const series = opt.series as any[];
        expect(series[0].itemStyle.color).toBe('#10b981');
        expect(series[1].itemStyle.color).toBe('#f43f5e');
    });

    it('configures axis trigger tooltip', () => {
        const opt = buildMonthlyReportOption(SAMPLE);
        const tooltip = opt.tooltip as any;
        expect(tooltip.trigger).toBe('axis');
        expect(typeof tooltip.formatter).toBe('function');
    });

    it('handles string income/expense values', () => {
        const data: MonthlyReport[] = [
            { year: 2026, month: 1, label: 'Ene 2026', income: '150000.50' as any, expense: '80000' as any, result: 70000 },
        ];
        const opt = buildMonthlyReportOption(data);
        const series = opt.series as any[];
        expect(series[0].data).toEqual([150000.50]);
        expect(series[1].data).toEqual([80000]);
    });

    it('handles empty data', () => {
        const opt = buildMonthlyReportOption([]);
        const series = opt.series as any[];
        expect(series[0].data).toEqual([]);
        expect(series[1].data).toEqual([]);
        expect((opt.xAxis as any).data).toEqual([]);
    });

    it('includes legend at bottom', () => {
        const opt = buildMonthlyReportOption(SAMPLE);
        const legend = opt.legend as any;
        expect(legend.show).toBe(true);
        expect(legend.bottom).toBe(0);
    });
});
