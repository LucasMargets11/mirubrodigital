# Chart System — Developer Guide

> Base establecida: **Apache ECharts ^5.6.0** (tree-shaked, **SVG renderer**).  
> Última migración: marzo 2026 — se eliminó recharts y todas las barras CSS manuales.  
> Renderer cambiado de canvas → SVG para nitidez nativa en texto/líneas a cualquier DPR.

---

## Componentes compartidos

| Componente | Ubicación | Uso |
|---|---|---|
| `EChart` | `lib/charts/EChart.tsx` | Wrapper base: init, setOption (notMerge), ResizeObserver, dispose, loading spinner. |
| `HorizontalRankChart` | `lib/charts/HorizontalRankChart.tsx` | Barras horizontales de ranking/distribución. Builder puro `buildHorizontalRankOption()` exportado para testing. |
| `echarts-modules` | `lib/charts/echarts-modules.ts` | Registro centralizado de módulos (BarChart, LineChart, PieChart, Grid, Tooltip, Legend, SVGRenderer). |
| `theme` | `lib/charts/theme.ts` | Tokens de color, estilos de tooltip, gradientes. Fuente única de verdad para colores de charts. |
| `index` (barrel) | `lib/charts/index.ts` | Re-exporta `EChart`, `HorizontalRankChart`, y todo `theme`. |

---

## Charts activos

| Chart | Archivo | Tipo visual |
|---|---|---|
| Tendencia de ventas | `components/reports/charts/SalesTrendChart.tsx` | Línea + barras, dual yAxis |
| Distribución de pagos | `components/reports/charts/PaymentsDonutChart.tsx` | Donut + legend JSX |
| Reporte mensual (finanzas) | `app/.../finanzas/reportes/reportes-client.tsx` | Barras agrupadas ingresos/egresos |
| Top productos (dashboard) | `app/.../dashboard/.../sales-trend-block.tsx` | `HorizontalRankChart` |
| Top productos (reportes) | `app/.../reportes/components/top-products-widget.tsx` | `HorizontalRankChart` |
| Mix de productos | `app/.../reportes/productos/products-client.tsx` | `HorizontalRankChart` |
| Distribuciones admin | `app/admin/reportes/reportes-content.tsx` | `HorizontalRankChart` |

---

## Cómo agregar un chart nuevo

1. **Crear un builder puro** (`buildXxxOption(data): EChartsCoreOption`) en el archivo del chart.
   - La función recibe datos ya tipados y retorna un objeto de opción puro.  
   - Exportarla para poder testearla sin DOM.

2. **Usar tokens de `lib/charts/theme`**:
   - Colores: `COLOR_PRIMARY`, `COLOR_SECONDARY`, `CATEGORICAL_PALETTE`, `COLOR_AXIS_LABEL`, `COLOR_GRID_LINE`.
   - Tooltip: spread `TOOLTIP_BASE_STYLE` y agregar `trigger` + `formatter`.
   - Gradiente: `primaryAreaGradient()` para areaStyle.

3. **Renderizar con `<EChart>`**:
   ```tsx
   const option = useMemo(() => buildXxxOption(data), [data]);
   return <EChart option={option} height={300} />;
   ```

4. **Si es un ranking/distribución horizontal**, usar `<HorizontalRankChart>` directamente:
   ```tsx
   <HorizontalRankChart
     items={[{ name: 'Producto A', value: 42 }]}
     formatLabel={(v) => `${v}%`}
     color="#312e81"
   />
   ```

5. **Si necesitás un tipo de chart nuevo** (scatter, heatmap, etc.):
   - Agregarlo en `echarts-modules.ts` (import + `echarts.use([...])`).
   - Verificar que el bundle no crezca más de lo necesario.

---

## Convenciones

- **No crear barras CSS/div manuales para data visualization**. Usar siempre la base ECharts.
- **Tooltip**: siempre `TOOLTIP_BASE_STYLE` como base. Heading en `font-weight:600`, valores en monospace.
- **Ejes**: labels en `COLOR_AXIS_LABEL`, grid lines en `COLOR_GRID_LINE`, dashed.
- **Barras**: `borderRadius: [4,4,0,0]` para barras verticales, `[0,4,4,0]` para horizontales.
- **`useMemo`**: siempre llamar hooks ANTES de cualquier early return (Rules of Hooks).
- **Colores**: preferir tokens del theme. Si un color es semántico del dominio (ej. income=emerald, expense=rose), definirlo como constante en el archivo del chart con un comentario.
- **Tests**: exportar el builder puro y testear la estructura de la opción resultante (series, categories, tooltips). No es necesario testear el render de ECharts en jsdom — ya está cubierto por los tests del wrapper.

---

## Registrar módulos ECharts

El archivo `echarts-modules.ts` controla qué se incluye en el bundle. Solo agregar lo que se necesita:

```ts
// echarts-modules.ts — agregar import y registrar en use()
import { ScatterChart } from 'echarts/charts';
echarts.use([..., ScatterChart]);
```

Módulos registrados actualmente: `BarChart`, `LineChart`, `PieChart`, `GridComponent`, `TooltipComponent`, `LegendComponent`, `CanvasRenderer`.
