/**
 * Centralised ECharts module registration with tree-shaking.
 *
 * Import this module ONCE (e.g. in the EChart wrapper) to register only the
 * chart types, components and renderer the app actually uses.
 *
 * To add a new chart type later, import it here and add it to the `use()` call.
 */
import * as echarts from 'echarts/core';

// --- chart types ---
import { BarChart } from 'echarts/charts';
import { LineChart } from 'echarts/charts';
import { PieChart } from 'echarts/charts';

// --- components (overlays, axes, layout) ---
import { GridComponent } from 'echarts/components';
import { TooltipComponent } from 'echarts/components';
import { LegendComponent } from 'echarts/components';

// --- renderers (both registered so runtime A/B via ?chart_renderer=svg|canvas works) ---
import { CanvasRenderer } from 'echarts/renderers';
import { SVGRenderer } from 'echarts/renderers';

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CanvasRenderer,
  SVGRenderer,
]);

export { echarts };
