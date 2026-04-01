/**
 * Mirubro chart theme – shared colour tokens and visual defaults.
 *
 * Keep this file as the single source of truth for chart colours so
 * individual chart components never hard-code hex values.
 */

// ── Core palette ─────────────────────────────────────────────
/** Primary indigo used for area fills and main series */
export const COLOR_PRIMARY = '#312e81';
/** Secondary purple used for bars / accent series */
export const COLOR_SECONDARY = '#c084fc';

/** Categorical palette for multi-series / pie charts (ordered) */
export const CATEGORICAL_PALETTE = [
  '#312e81', // indigo-900
  '#7c3aed', // violet-600
  '#0f766e', // teal-700
  '#be123c', // rose-700
  '#fb923c', // orange-400
  '#0ea5e9', // sky-500
  '#14b8a6', // teal-400
  '#a21caf', // fuchsia-700
  '#2563eb', // blue-600
  '#6b7280', // gray-500
];

// ── Axis / grid defaults ─────────────────────────────────────
export const COLOR_AXIS_LABEL = '#94a3b8'; // slate-400
export const COLOR_GRID_LINE = '#e2e8f0';  // slate-200

// ── Gradient helper ──────────────────────────────────────────
/**
 * Builds a vertical linear gradient suitable for ECharts `areaStyle.color`.
 * Uses the echarts graphic API at render-time so import is deferred.
 */
export function primaryAreaGradient() {
  // Lazy-require to avoid importing echarts at module-evaluation time in tests
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { graphic } = require('echarts/core');
  return new graphic.LinearGradient(0, 0, 0, 1, [
    { offset: 0, color: 'rgba(49,46,129,0.18)' },
    { offset: 0.7, color: 'rgba(49,46,129,0.04)' },
    { offset: 1, color: 'rgba(49,46,129,0)' },
  ]);
}

// ── Tooltip baseline style ───────────────────────────────────
/** Re-usable tooltip container style matching the Tailwind card look */
export const TOOLTIP_BASE_STYLE = {
  backgroundColor: '#ffffff',
  borderColor: '#e2e8f0',
  borderWidth: 1,
  borderRadius: 10,
  padding: [12, 16],
  appendToBody: true,
  /**
   * `will-change:auto !important` overrides the `will-change:transform` that
   * ECharts hardcodes on every tooltip div (TooltipHTMLContent.js line 55).
   * That permanent GPU-layer promotion + CSS transition on translate3d causes
   * grayscale-AA text on Windows Chrome → visibly blurry first openings.
   */
  extraCssText:
    'will-change:auto !important;'
    + 'box-shadow:0 4px 24px rgba(0,0,0,.08),0 1px 3px rgba(0,0,0,.06);',
  textStyle: {
    color: '#334155', // slate-700
    fontSize: 13,
  },
  /**
   * MUST be 0.  Any value > 0 adds a CSS transition on `transform` (the
   * translate3d used for positioning).  During the transition Chrome promotes
   * the tooltip to a GPU compositor layer and renders text with grayscale AA
   * instead of ClearType — producing visible blur on the first 2-3 openings
   * until the compositor cache stabilises.
   */
  transitionDuration: 0,
} as const;
