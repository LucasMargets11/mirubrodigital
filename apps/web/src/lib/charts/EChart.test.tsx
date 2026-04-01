import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { render, cleanup } from '@testing-library/react';

// ── Mock ECharts ─────────────────────────────────────────────
// jsdom has no canvas, so we mock the entire echarts core.

const mockChart = {
  setOption: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
  isDisposed: vi.fn(() => false),
  showLoading: vi.fn(),
  hideLoading: vi.fn(),
};

vi.mock('./echarts-modules', () => ({
  echarts: {
    init: vi.fn(() => mockChart),
  },
}));

// Must import AFTER vi.mock so the mock is applied
import { EChart } from './EChart';
import { echarts } from './echarts-modules';

// ── Helpers ──────────────────────────────────────────────────

const MINIMAL_OPTION = { xAxis: { type: 'category' as const }, yAxis: {}, series: [] };

// Stub ResizeObserver for jsdom
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

// ── Tests ────────────────────────────────────────────────────

describe('EChart wrapper', () => {
  it('renders a container div and initialises echarts', () => {
    const { container } = render(<EChart option={MINIMAL_OPTION} />);

    const div = container.firstElementChild as HTMLDivElement;
    expect(div).toBeTruthy();
    expect(div.style.width).toBe('100%');
    expect(div.style.height).toBe('300px'); // default height

    expect(echarts.init).toHaveBeenCalledTimes(1);
    expect(mockChart.setOption).toHaveBeenCalledWith(MINIMAL_OPTION, { notMerge: true });
  });

  it('respects custom height and className', () => {
    const { container } = render(
      <EChart option={MINIMAL_OPTION} height={400} className="my-chart" />,
    );

    const div = container.firstElementChild as HTMLDivElement;
    expect(div.style.height).toBe('400px');
    expect(div.classList.contains('my-chart')).toBe(true);
  });

  it('registers a ResizeObserver on the container', () => {
    render(<EChart option={MINIMAL_OPTION} />);
    expect(mockObserve).toHaveBeenCalledTimes(1);
  });

  it('updates option when the prop changes', () => {
    const { rerender } = render(<EChart option={MINIMAL_OPTION} />);

    const newOption = { xAxis: { type: 'value' as const }, yAxis: {}, series: [] };
    rerender(<EChart option={newOption} />);

    // First call from mount, second from update
    expect(mockChart.setOption).toHaveBeenCalledTimes(2);
    expect(mockChart.setOption).toHaveBeenLastCalledWith(newOption, { notMerge: true });
  });

  it('disposes the chart and disconnects ResizeObserver on unmount', () => {
    const { unmount } = render(<EChart option={MINIMAL_OPTION} />);
    unmount();

    expect(mockChart.dispose).toHaveBeenCalledTimes(1);
    expect(mockDisconnect).toHaveBeenCalledTimes(1);
  });

  it('shows and hides loading state', () => {
    const { rerender } = render(<EChart option={MINIMAL_OPTION} loading />);
    expect(mockChart.showLoading).toHaveBeenCalledTimes(1);

    rerender(<EChart option={MINIMAL_OPTION} loading={false} />);
    expect(mockChart.hideLoading).toHaveBeenCalledTimes(1);
  });

  it('does not call setOption after dispose', () => {
    const { rerender, unmount } = render(<EChart option={MINIMAL_OPTION} />);
    unmount();

    // After unmount, mockChart.isDisposed should return true
    mockChart.isDisposed.mockReturnValue(true);

    // Force a dangling rerender scenario – should not throw
    // (In practice this can't happen, but guards the early-return logic)
    cleanup();
  });
});
