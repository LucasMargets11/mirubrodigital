import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { CATEGORICAL_PALETTE, COLOR_AXIS_LABEL } from './theme';

// ── Mock ECharts (jsdom has no canvas) ───────────────────────
const mockChart = {
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    isDisposed: vi.fn(() => false),
    showLoading: vi.fn(),
    hideLoading: vi.fn(),
};

vi.mock('./echarts-modules', () => ({
    echarts: { init: vi.fn(() => mockChart) },
}));

// Import after mock
import { buildHorizontalRankOption, HorizontalRankChart } from './HorizontalRankChart';

// Stub ResizeObserver
const mockObserve = vi.fn();
const mockDisconnect = vi.fn();
class FakeResizeObserver {
    observe = mockObserve;
    unobserve = vi.fn();
    disconnect = mockDisconnect;
}

beforeEach(() => {
    vi.clearAllMocks();
    mockChart.isDisposed.mockReturnValue(false);
    globalThis.ResizeObserver = FakeResizeObserver as unknown as typeof ResizeObserver;
});

// ── Helpers ──────────────────────────────────────────────────
const SAMPLE: Parameters<typeof buildHorizontalRankOption>[0] = [
    { name: 'Hamburguesa', value: 5000 },
    { name: 'Pizza', value: 3200 },
    { name: 'Empanada', value: 1800 },
];

// ── Tests ────────────────────────────────────────────────────
describe('buildHorizontalRankOption', () => {
    it('reverses items so #1 appears at top', () => {
        const opt = buildHorizontalRankOption(SAMPLE) as any;
        // yAxis categories should be reversed (bottom→top in ECharts = top→bottom visually)
        expect(opt.yAxis.data).toEqual(['Empanada', 'Pizza', 'Hamburguesa']);
    });

    it('uses category yAxis and value xAxis', () => {
        const opt = buildHorizontalRankOption(SAMPLE) as any;
        expect(opt.yAxis.type).toBe('category');
        expect(opt.xAxis.type).toBe('value');
    });

    it('hides xAxis labels, lines, and ticks', () => {
        const opt = buildHorizontalRankOption(SAMPLE) as any;
        expect(opt.xAxis.axisLabel.show).toBe(false);
        expect(opt.xAxis.splitLine.show).toBe(false);
        expect(opt.xAxis.axisLine.show).toBe(false);
    });

    it('produces a single bar series with reversed values', () => {
        const opt = buildHorizontalRankOption(SAMPLE) as any;
        expect(opt.series).toHaveLength(1);
        expect(opt.series[0].type).toBe('bar');
        expect(opt.series[0].data).toEqual([1800, 3200, 5000]);
    });

    it('defaults bar colour to CATEGORICAL_PALETTE[0]', () => {
        const opt = buildHorizontalRankOption(SAMPLE) as any;
        expect(opt.series[0].itemStyle.color).toBe(CATEGORICAL_PALETTE[0]);
    });

    it('applies custom colour', () => {
        const opt = buildHorizontalRankOption(SAMPLE, { color: '#ff0000' }) as any;
        expect(opt.series[0].itemStyle.color).toBe('#ff0000');
    });

    it('applies formatLabel to bar labels', () => {
        const fmt = (v: number) => `$${v}`;
        const opt = buildHorizontalRankOption(SAMPLE, { formatLabel: fmt }) as any;
        // The label formatter is a function — call it to verify
        const labelFn = opt.series[0].label.formatter;
        expect(labelFn({ value: 5000 })).toBe('$5000');
    });

    it('uses yAxis colour from theme', () => {
        const opt = buildHorizontalRankOption(SAMPLE) as any;
        expect(opt.yAxis.axisLabel.color).toBe(COLOR_AXIS_LABEL);
    });

    it('returns empty categories/values when items is empty', () => {
        const opt = buildHorizontalRankOption([]) as any;
        expect(opt.yAxis.data).toEqual([]);
        expect(opt.series[0].data).toEqual([]);
    });

    it('tooltip formatter calls custom formatTooltip with original index', () => {
        const spy = vi.fn(() => '<b>custom</b>');
        const opt = buildHorizontalRankOption(SAMPLE, { formatTooltip: spy }) as any;

        // Simulate ECharts calling the formatter for the first reversed item (dataIndex 0 = original last)
        const result = opt.tooltip.formatter({ name: 'Empanada', value: 1800, dataIndex: 0 });
        expect(spy).toHaveBeenCalledWith('Empanada', 1800, 2); // originalIdx = 3-1-0 = 2
        expect(result).toBe('<b>custom</b>');
    });

    it('default tooltip includes name and formatted value', () => {
        const fmt = (v: number) => `ARS ${v}`;
        const opt = buildHorizontalRankOption(SAMPLE, { formatLabel: fmt }) as any;
        const html = opt.tooltip.formatter({ name: 'Pizza', value: 3200, dataIndex: 1 });
        expect(html).toContain('Pizza');
        expect(html).toContain('ARS 3200');
    });
});

describe('HorizontalRankChart component', () => {
    it('renders without crashing', () => {
        const { container } = render(<HorizontalRankChart items={SAMPLE} />);
        expect(container.firstChild).toBeTruthy();
    });

    it('computes auto-height from item count', () => {
        const { container } = render(<HorizontalRankChart items={SAMPLE} />);
        const div = container.firstChild as HTMLElement;
        // Auto height = items.length * 36 + 16 = 3*36+16 = 124
        expect(div.style.height).toBe('124px');
    });

    it('uses explicit height when provided', () => {
        const { container } = render(<HorizontalRankChart items={SAMPLE} height={300} />);
        const div = container.firstChild as HTMLElement;
        expect(div.style.height).toBe('300px');
    });
});
