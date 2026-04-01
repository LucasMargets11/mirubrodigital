import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';

// ── Mock ECharts ─────────────────────────────────────────────

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

import { PaymentsDonutChart, type PaymentsDonutChartProps } from './PaymentsDonutChart';
import { buildDonutOption } from './PaymentsDonutChart';
import type { PaymentBreakdownRow } from '@/features/reports/types';

// ── Fixtures ─────────────────────────────────────────────────

const SAMPLE_DATA: PaymentBreakdownRow[] = [
  { method: 'CASH', method_label: 'Efectivo', amount_total: '50000.00', payments_count: 20, sales_count: 18 },
  { method: 'CARD', method_label: 'Tarjeta', amount_total: '30000.00', payments_count: 15, sales_count: 14 },
  { method: 'TRANSFER', method_label: 'Transferencia', amount_total: '20000.00', payments_count: 10, sales_count: 9 },
];

const EMPTY_DATA: PaymentBreakdownRow[] = [];

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

// ── Component tests ──────────────────────────────────────────

describe('PaymentsDonutChart', () => {
  it('renders without crashing', () => {
    const { container } = render(<PaymentsDonutChart data={SAMPLE_DATA} />);
    expect(container.firstElementChild).toBeTruthy();
  });

  it('returns null for empty data', () => {
    const { container } = render(<PaymentsDonutChart data={EMPTY_DATA} />);
    expect(container.firstElementChild).toBeNull();
  });

  it('renders the JSX sidebar legend with correct labels', () => {
    const { getByText } = render(<PaymentsDonutChart data={SAMPLE_DATA} />);
    expect(getByText('Efectivo')).toBeTruthy();
    expect(getByText('Tarjeta')).toBeTruthy();
    expect(getByText('Transferencia')).toBeTruthy();
  });

  it('renders payment counts in the legend', () => {
    const { getByText } = render(<PaymentsDonutChart data={SAMPLE_DATA} />);
    expect(getByText('20 pagos')).toBeTruthy();
    expect(getByText('15 pagos')).toBeTruthy();
    expect(getByText('10 pagos')).toBeTruthy();
  });

  it('renders percentage values in the legend', () => {
    const { getByText } = render(<PaymentsDonutChart data={SAMPLE_DATA} />);
    expect(getByText('50.0%')).toBeTruthy(); // 50k / 100k
    expect(getByText('30.0%')).toBeTruthy();
    expect(getByText('20.0%')).toBeTruthy();
  });

  it('preserves the public API contract (props shape)', () => {
    const props: PaymentsDonutChartProps = { data: SAMPLE_DATA, topN: 3 };
    const { container } = render(<PaymentsDonutChart {...props} />);
    expect(container.firstElementChild).toBeTruthy();
  });

  it('passes an ECharts option to setOption', () => {
    render(<PaymentsDonutChart data={SAMPLE_DATA} />);
    expect(mockChart.setOption).toHaveBeenCalledTimes(1);
    const [option] = mockChart.setOption.mock.calls[0];
    expect(option).toHaveProperty('series');
    expect(option).toHaveProperty('tooltip');
  });
});

// ── Option builder tests ─────────────────────────────────────

describe('buildDonutOption', () => {
  const prepared = [
    { method: 'CASH', label: 'Efectivo', value: 50000, payments_count: 20, percent: 50, color: '#0f766e' },
    { method: 'CARD', label: 'Tarjeta', value: 30000, payments_count: 15, percent: 30, color: '#7c3aed' },
    { method: 'TRANSFER', label: 'Transferencia', value: 20000, payments_count: 10, percent: 20, color: '#2563eb' },
  ];

  it('creates a single pie series', () => {
    const option = buildDonutOption(prepared);
    const series = option.series as Array<{ type: string }>;
    expect(series).toHaveLength(1);
    expect(series[0].type).toBe('pie');
  });

  it('configures donut radius (inner + outer)', () => {
    const option = buildDonutOption(prepared);
    const series = option.series as Array<{ radius: string[] }>;
    expect(series[0].radius).toEqual(['60%', '85%']);
  });

  it('maps data items with correct values and semantic colours', () => {
    const option = buildDonutOption(prepared);
    const series = option.series as Array<{ data: Array<{ name: string; value: number; itemStyle: { color: string } }> }>;
    const items = series[0].data;
    expect(items).toHaveLength(3);
    expect(items[0].name).toBe('Efectivo');
    expect(items[0].value).toBe(50000);
    expect(items[0].itemStyle.color).toBe('#0f766e');
    expect(items[1].itemStyle.color).toBe('#7c3aed');
    expect(items[2].itemStyle.color).toBe('#2563eb');
  });

  it('hides pie labels (legend is JSX sidebar)', () => {
    const option = buildDonutOption(prepared);
    const series = option.series as Array<{ label: { show: boolean } }>;
    expect(series[0].label.show).toBe(false);
  });

  it('has a tooltip with item trigger and formatter', () => {
    const option = buildDonutOption(prepared);
    const tooltip = option.tooltip as { trigger: string; formatter: Function };
    expect(tooltip.trigger).toBe('item');
    expect(typeof tooltip.formatter).toBe('function');
  });

  it('tooltip formatter returns HTML with payment details', () => {
    const option = buildDonutOption(prepared);
    const tooltip = option.tooltip as { formatter: Function };
    const html = tooltip.formatter({
      data: { label: 'Efectivo', value: 50000, payments_count: 20, percent: 50 },
    });
    expect(html).toContain('Efectivo');
    expect(html).toContain('Pagos: 20');
    expect(html).toContain('50.0%');
  });
});
