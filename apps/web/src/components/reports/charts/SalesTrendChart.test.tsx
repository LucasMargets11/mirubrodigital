import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';

// ── Mock ECharts (same pattern as EChart.test.tsx) ───────────

const mockChart = {
  setOption: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
  isDisposed: vi.fn(() => false),
  showLoading: vi.fn(),
  hideLoading: vi.fn(),
};

vi.mock('@/lib/charts/echarts-modules', () => ({
  echarts: { init: vi.fn(() => mockChart) },
}));

vi.mock('@/lib/charts/theme', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/charts/theme')>();
  return {
    ...actual,
    // Replace the gradient helper so it doesn't require real echarts/core
    primaryAreaGradient: () => 'mock-gradient',
  };
});

import { SalesTrendChart, type SalesTrendChartProps } from './SalesTrendChart';
import { buildSalesTrendOption } from './SalesTrendChart';
import type { TrendPoint } from '../utils/fillMissingPeriods';

// ── Fixtures ─────────────────────────────────────────────────

const SAMPLE_DATA: TrendPoint[] = [
  { period: '2026-03-01', gross_sales: '150000.00', sales_count: 42, avg_ticket: '3571.43' },
  { period: '2026-03-02', gross_sales: '200000.50', sales_count: 55, avg_ticket: '3636.37' },
  { period: '2026-03-03', gross_sales: '0.00', sales_count: 0, avg_ticket: '0.00' },
];

const EMPTY_DATA: TrendPoint[] = [];

// ── Helpers ──────────────────────────────────────────────────

class FakeResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}

beforeEach(() => {
  vi.clearAllMocks();
  mockChart.isDisposed.mockReturnValue(false);
  globalThis.ResizeObserver = FakeResizeObserver as unknown as typeof ResizeObserver;
});

// ── Tests ────────────────────────────────────────────────────

describe('SalesTrendChart', () => {
  it('renders without crashing', () => {
    const { container } = render(<SalesTrendChart data={SAMPLE_DATA} />);
    expect(container.firstElementChild).toBeTruthy();
  });

  it('renders with empty data', () => {
    const { container } = render(<SalesTrendChart data={EMPTY_DATA} />);
    expect(container.firstElementChild).toBeTruthy();
  });

  it('passes an ECharts option to setOption', () => {
    render(<SalesTrendChart data={SAMPLE_DATA} />);
    expect(mockChart.setOption).toHaveBeenCalledTimes(1);

    const [option] = mockChart.setOption.mock.calls[0];
    expect(option).toHaveProperty('xAxis');
    expect(option).toHaveProperty('yAxis');
    expect(option).toHaveProperty('series');
    expect(option).toHaveProperty('tooltip');
  });

  it('preserves the public API contract (props shape)', () => {
    // TypeScript compile-time check – this would fail if the type changed
    const props: SalesTrendChartProps = { data: SAMPLE_DATA };
    const { container } = render(<SalesTrendChart {...props} />);
    expect(container.firstElementChild).toBeTruthy();
  });
});

describe('buildSalesTrendOption', () => {
  it('maps data points to xAxis categories', () => {
    const option = buildSalesTrendOption(SAMPLE_DATA);
    const xAxis = option.xAxis as { data: string[] };
    expect(xAxis.data).toHaveLength(3);
  });

  it('creates two series (bar + line)', () => {
    const option = buildSalesTrendOption(SAMPLE_DATA);
    const series = option.series as Array<{ type: string; name: string }>;
    expect(series).toHaveLength(2);
    expect(series[0].type).toBe('bar');
    expect(series[0].name).toBe('Cantidad de ventas');
    expect(series[1].type).toBe('line');
    expect(series[1].name).toBe('Ventas brutas');
  });

  it('configures dual y-axes (left = currency, right = count)', () => {
    const option = buildSalesTrendOption(SAMPLE_DATA);
    const yAxis = option.yAxis as Array<{ position: string }>;
    expect(yAxis).toHaveLength(2);
    expect(yAxis[0].position).toBe('left');
    expect(yAxis[1].position).toBe('right');
  });

  it('bar series uses yAxisIndex 1 and line series uses yAxisIndex 0', () => {
    const option = buildSalesTrendOption(SAMPLE_DATA);
    const series = option.series as Array<{ yAxisIndex: number }>;
    expect(series[0].yAxisIndex).toBe(1); // bar → right axis
    expect(series[1].yAxisIndex).toBe(0); // line → left axis
  });

  it('bar series data matches sales_count values', () => {
    const option = buildSalesTrendOption(SAMPLE_DATA);
    const series = option.series as Array<{ data: number[] }>;
    expect(series[0].data).toEqual([42, 55, 0]);
  });

  it('line series data matches gross_sales values (numeric)', () => {
    const option = buildSalesTrendOption(SAMPLE_DATA);
    const series = option.series as Array<{ data: number[] }>;
    expect(series[1].data).toEqual([150000, 200000.5, 0]);
  });

  it('returns valid option for empty data', () => {
    const option = buildSalesTrendOption(EMPTY_DATA);
    const xAxis = option.xAxis as { data: string[] };
    expect(xAxis.data).toHaveLength(0);
    const series = option.series as Array<{ data: number[] }>;
    expect(series[0].data).toHaveLength(0);
    expect(series[1].data).toHaveLength(0);
  });

  it('has a tooltip with a formatter function', () => {
    const option = buildSalesTrendOption(SAMPLE_DATA);
    const tooltip = option.tooltip as { formatter: Function };
    expect(typeof tooltip.formatter).toBe('function');
  });
});
