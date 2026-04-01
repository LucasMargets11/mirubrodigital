'use client';

import { useRef, useEffect, type CSSProperties } from 'react';
import type { ECharts, EChartsCoreOption } from 'echarts/core';
import { echarts } from './echarts-modules';

// ── Props ────────────────────────────────────────────────────

export type EChartProps = {
  /** Full ECharts option object. Shallow-compared by reference. */
  option: EChartsCoreOption;
  /** Container height – pixels or CSS string like '100%' (default 300). */
  height?: number | string;
  /** Extra CSS class names for the container div. */
  className?: string;
  /** Show the built-in ECharts loading spinner. */
  loading?: boolean;
};

// ── A/B renderer override via URL: ?chart_renderer=svg|canvas ──

function getRendererOverride(): 'canvas' | 'svg' | null {
  if (typeof window === 'undefined') return null;
  const r = new URLSearchParams(window.location.search).get('chart_renderer');
  return r === 'svg' || r === 'canvas' ? r : null;
}

// ── Runtime diagnostics (dev only, ?chart_debug in URL) ─────

function runDiagnostics(el: HTMLElement, renderer: string) {
  if (typeof window === 'undefined') return;
  if (!new URLSearchParams(window.location.search).has('chart_debug')) return;

  const dpr = window.devicePixelRatio || 1;
  const rect = el.getBoundingClientRect();
  const canvas = el.querySelector('canvas');
  const svg = el.querySelector('svg');
  const actual = canvas ? 'canvas' : svg ? 'svg' : 'unknown';

  console.group('%c[EChart Diag]', 'color:#6366f1;font-weight:bold');
  console.log('Renderer:', actual, `(requested: ${renderer})`);
  console.log('DPR native:', dpr, '→ forced:', Math.max(dpr, 2));
  console.log(
    'Container:',
    `${rect.width.toFixed(1)}×${rect.height.toFixed(1)}`,
    Number.isInteger(rect.width) && Number.isInteger(rect.height)
      ? '✅ integer'
      : '⚠️ fractional',
  );
  if (canvas) {
    console.log(
      'Canvas:',
      `${canvas.width}×${canvas.height}`,
      `(${(canvas.width / rect.width).toFixed(2)}x oversample)`,
    );
  }

  // Walk ancestors for problematic CSS properties
  const issues: string[] = [];
  let node = el.parentElement;
  let depth = 0;
  while (node && depth < 20) {
    const cs = getComputedStyle(node);
    const found: string[] = [];
    if (cs.transform !== 'none') found.push(`transform:${cs.transform}`);
    if (cs.filter !== 'none') found.push(`filter:${cs.filter}`);
    if (cs.backdropFilter && cs.backdropFilter !== 'none')
      found.push(`backdrop-filter:${cs.backdropFilter}`);
    if (cs.opacity !== '1') found.push(`opacity:${cs.opacity}`);
    if (cs.willChange !== 'auto') found.push(`will-change:${cs.willChange}`);
    if (cs.perspective && cs.perspective !== 'none') found.push('perspective');
    const zoom = (cs as unknown as Record<string, unknown>).zoom;
    if (zoom && zoom !== '1' && zoom !== 'normal' && zoom !== '')
      found.push(`zoom:${zoom}`);
    if (found.length) {
      const tag = `${node.tagName.toLowerCase()}.${Array.from(node.classList).slice(0, 3).join('.')}`;
      issues.push(`[d=${depth}] ${tag} → ${found.join(', ')}`);
    }
    node = node.parentElement;
    depth++;
  }

  if (issues.length) {
    console.warn('⚠️ Ancestor CSS issues:', issues);
  } else {
    console.log('Ancestors: ✅ clean');
  }
  console.groupEnd();
}

// ── Component ────────────────────────────────────────────────

const DEFAULT_HEIGHT = 300;

export function EChart({
  option,
  height = DEFAULT_HEIGHT,
  className,
  loading = false,
}: EChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ECharts | null>(null);

  // Init & dispose
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    // Default: canvas + forced DPR ≥ 2 for crisp text on low-DPR Windows displays.
    // Override via ?chart_renderer=svg for A/B comparison in browser.
    const renderer = getRendererOverride() ?? 'canvas';

    // Force minimum 2× oversampling so canvas text gets effectively sub-pixel
    // quality even on DPR-1 monitors. For SVG the option is ignored by ECharts.
    const dpr = Math.max(window.devicePixelRatio || 1, 2);

    const chart = echarts.init(el, undefined, {
      renderer,
      devicePixelRatio: dpr,
    });
    chartRef.current = chart;

    // Responsive resize with integer-rounded dimensions to avoid sub-pixel blur.
    const ro = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height: h } = entry.contentRect;
      chart.resize({ width: Math.round(width), height: Math.round(h) });
    });
    ro.observe(el);

    // Dev diagnostics (only if ?chart_debug is in URL)
    if (process.env.NODE_ENV === 'development') {
      requestAnimationFrame(() => runDiagnostics(el, renderer));
    }

    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []); // mount-only

  // Update option
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || chart.isDisposed()) return;
    chart.setOption(option, { notMerge: true });
  }, [option]);

  // Loading state
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || chart.isDisposed()) return;
    if (loading) {
      chart.showLoading('default', {
        text: '',
        maskColor: 'rgba(255,255,255,0.7)',
        zlevel: 0,
      });
    } else {
      chart.hideLoading();
    }
  }, [loading]);

  const style: CSSProperties = { width: '100%', height };

  return <div ref={containerRef} className={className} style={style} />;
}
