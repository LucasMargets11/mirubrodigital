'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Check, Info, Zap } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  QR_FEATURE_CATALOG,
  QR_ADDONS,
  PRO_MODULE_OPTIONS,
  type QrFeatureEntry,
  type ProModule,
} from '../data/menu-qr-catalog';

// ---------------------------------------------------------------------------
// Pro state (lifted from plan builder)
// ---------------------------------------------------------------------------

export interface QrProState {
  proIncludedModule: ProModule | null;
  proAddonEnabled: boolean;
}

// ---------------------------------------------------------------------------
// Resolved cell status — 5 distinct display states
// ---------------------------------------------------------------------------

type ResolvedCellStatus =
  | 'included'           // ✅ Directly included in plan price
  | 'included_via_addon' // ✅ Active because user enabled the add-on
  | 'addon_available'    // ➕ Can be purchased as add-on (not currently active)
  | 'pro_chooseable'     // ⚡ PRO conditional, module not selected yet
  | 'not_included';      // — Not available in this plan

function resolveProConditional(
  featureKey: string,
  proState: QrProState,
): ResolvedCellStatus {
  const { proIncludedModule, proAddonEnabled } = proState;
  const isReviews = featureKey === 'menu_qr_reviews';
  const isTips = featureKey === 'menu_qr_tips';
  if (!isReviews && !isTips) return 'not_included';
  if (proIncludedModule === null) return 'pro_chooseable';
  const directlyIncluded =
    (isReviews && proIncludedModule === 'reviews') ||
    (isTips && proIncludedModule === 'tips');
  if (directlyIncluded) return 'included';
  // It's the "other" conditional module
  return proAddonEnabled ? 'included_via_addon' : 'addon_available';
}

function resolveCellStatus(
  feature: QrFeatureEntry,
  planKey: 'lite' | 'pro' | 'premium',
  proState: QrProState,
): ResolvedCellStatus {
  const raw = feature.availability[planKey];
  if (raw === 'included') return 'included';
  if (raw === 'not_included') return 'not_included';
  if (raw === 'addon') return 'addon_available';
  if (raw === 'conditional') return resolveProConditional(feature.key, proState);
  return 'not_included';
}

function rankForPlan(
  feature: QrFeatureEntry,
  planKey: 'lite' | 'pro' | 'premium',
  proState: QrProState,
): 0 | 1 | 2 {
  const status = resolveCellStatus(feature, planKey, proState);
  if (status === 'included' || status === 'included_via_addon') return 0;
  if (status === 'addon_available' || status === 'pro_chooseable') return 1;
  return 2;
}

/** Features sorted by (rank for the given plan, original catalog order) */
function sortedFeatures(
  planKey: 'lite' | 'pro' | 'premium',
  proState: QrProState,
): QrFeatureEntry[] {
  return QR_FEATURE_CATALOG
    .map((f, idx) => ({ f, idx }))
    .sort((a, b) => {
      const ra = rankForPlan(a.f, planKey, proState);
      const rb = rankForPlan(b.f, planKey, proState);
      if (ra !== rb) return ra - rb;
      return a.idx - b.idx;
    })
    .map(({ f }) => f);
}

// ---------------------------------------------------------------------------
// Tooltip — same portal-based pattern as GestionComercialComparisonTable
// ---------------------------------------------------------------------------

interface TooltipPos {
  top: number;
  left: number;
  placement: 'right' | 'left';
}

function FeatureInfoTooltip({ title, description }: { title: string; description: string }) {
  const [visible, setVisible] = useState(false);
  const [pos, setPos] = useState<TooltipPos>({ top: 0, left: 0, placement: 'right' });
  const triggerRef = useRef<HTMLButtonElement>(null);
  const TOOLTIP_WIDTH = 300;
  const GAP = 8;

  const calcPos = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const spaceRight = window.innerWidth - rect.right;
    const placement: 'right' | 'left' = spaceRight >= TOOLTIP_WIDTH + GAP * 2 ? 'right' : 'left';
    const left = placement === 'right' ? rect.right + GAP : rect.left - TOOLTIP_WIDTH - GAP;
    const top = rect.top + rect.height / 2 + window.scrollY;
    setPos({ top, left, placement });
  }, []);

  const show = useCallback(() => { calcPos(); setVisible(true); }, [calcPos]);
  const hide = useCallback(() => setVisible(false), []);

  useEffect(() => {
    if (!visible) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') hide(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [visible, hide]);

  const tooltipEl =
    typeof document !== 'undefined' && visible
      ? createPortal(
          <div
            role="tooltip"
            id={`qr-tip-${title.replace(/\s+/g, '-').toLowerCase()}`}
            style={{ position: 'absolute', top: pos.top, left: pos.left, width: TOOLTIP_WIDTH, transform: 'translateY(-50%)', zIndex: 9999 }}
            className="pointer-events-none rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 shadow-md"
          >
            <p className="text-xs font-semibold text-slate-800 mb-0.5">{title}</p>
            <p className="text-xs text-slate-500 leading-relaxed">{description}</p>
          </div>,
          document.body
        )
      : null;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-label={`Ver descripción de ${title}`}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        className="flex-shrink-0 rounded p-0.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 transition-colors"
      >
        <Info className="w-3.5 h-3.5" aria-hidden="true" />
      </button>
      {tooltipEl}
    </>
  );
}

// ---------------------------------------------------------------------------
// PlanMark — renders resolved cell status (5 states)
// ---------------------------------------------------------------------------

const STATUS_ARIA: Record<ResolvedCellStatus, string> = {
  included: 'Incluido',
  included_via_addon: 'Incluido vía add-on activo',
  addon_available: 'Disponible como add-on',
  pro_chooseable: 'A elegir en el plan PRO',
  not_included: 'No incluido',
};

function PlanMark({
  status,
  conditionalNote,
}: {
  status: ResolvedCellStatus;
  conditionalNote?: string;
}) {
  if (status === 'included') {
    return (
      <span
        aria-hidden="true"
        className="inline-flex w-[22px] h-[22px] rounded-full bg-indigo-400 items-center justify-center flex-shrink-0"
      >
        <Check className="w-3.5 h-3.5 text-white" strokeWidth={2.5} />
      </span>
    );
  }

  if (status === 'included_via_addon') {
    return (
      <span aria-hidden="true" className="inline-flex flex-col items-center gap-0.5">
        <span className="inline-flex w-[22px] h-[22px] rounded-full bg-indigo-400 items-center justify-center flex-shrink-0">
          <Check className="w-3.5 h-3.5 text-white" strokeWidth={2.5} />
        </span>
        <span className="text-[9px] font-semibold text-indigo-500 leading-none">add-on</span>
      </span>
    );
  }

  if (status === 'not_included') {
    return (
      <span
        aria-hidden="true"
        className="inline-flex w-[22px] h-[22px] rounded-full bg-slate-200 items-center justify-center flex-shrink-0"
      >
        <Check className="w-3.5 h-3.5 text-slate-100" strokeWidth={2.5} />
      </span>
    );
  }

  if (status === 'pro_chooseable') {
    return (
      <span
        aria-hidden="true"
        title={conditionalNote}
        className="inline-flex items-center gap-0.5 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700 leading-tight"
      >
        <Zap className="w-2.5 h-2.5" />
        A elegir
      </span>
    );
  }

  // addon_available
  return (
    <span aria-hidden="true" className="text-xs font-medium text-slate-500">
      Add-on
    </span>
  );
}

// ---------------------------------------------------------------------------
// Legend
// ---------------------------------------------------------------------------

const LEGEND_ENTRIES: { status: ResolvedCellStatus; label: string }[] = [
  { status: 'included', label: 'Incluido' },
  { status: 'included_via_addon', label: 'Incluido (add-on)' },
  { status: 'pro_chooseable', label: 'A elegir (PRO)' },
  { status: 'addon_available', label: 'Add-on' },
  { status: 'not_included', label: 'No incluido' },
];

function Legend() {
  return (
    <div role="note" aria-label="Referencias de la tabla" className="flex flex-wrap gap-x-6 gap-y-2">
      {LEGEND_ENTRIES.map(({ status, label }) => (
        <span key={status} className="flex items-center gap-2 text-xs text-slate-600">
          <PlanMark status={status} />
          <span>{label}</span>
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Feature row — cells resolved from proState
// ---------------------------------------------------------------------------

function FeatureRow({
  feature,
  rowIndex,
  proState,
}: {
  feature: QrFeatureEntry;
  rowIndex: number;
  proState: QrProState;
}) {
  const isOdd = rowIndex % 2 !== 0;
  const rowBg = isOdd ? 'bg-slate-50' : 'bg-white';

  const renderCell = (plan: 'lite' | 'pro' | 'premium') => {
    const status = resolveCellStatus(feature, plan, proState);
    return (
      <td key={plan} className={cn('py-3 px-3 text-center align-middle', rowBg)} role="cell">
        <PlanMark status={status} conditionalNote={feature.conditionalNote} />
        <span className="sr-only">
          {STATUS_ARIA[status]} en {plan.toUpperCase()} para {feature.title}
        </span>
      </td>
    );
  };

  return (
    <tr className={cn('border-b border-slate-100 transition-colors hover:bg-slate-100/60', rowBg)}>
      <th
        scope="row"
        className={cn(
          'py-3 pl-4 pr-2 text-left align-middle text-sm font-medium text-slate-800 sticky left-0 z-10 max-w-[220px]',
          rowBg
        )}
      >
        <div className="flex items-start gap-1.5">
          <span className="flex-1 leading-snug">{feature.title}</span>
          <FeatureInfoTooltip title={feature.title} description={feature.description} />
        </div>
      </th>
      {(['lite', 'pro', 'premium'] as const).map(renderCell)}
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Desktop table — flat sorted list, plan selector above
// ---------------------------------------------------------------------------

const PLAN_HEADER_COLORS: Record<string, string> = {
  LITE: 'text-slate-600',
  PRO: 'text-brand-700',
  PREMIUM: 'text-violet-700',
};

function DesktopTable({ proState }: { proState: QrProState }) {
  // Always sort by PRO plan + current proState (active features first)
  const features = sortedFeatures('pro', proState);

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 shadow-sm">
      <table className="min-w-full border-collapse text-sm" role="table">
        <caption className="sr-only">Comparativa de planes de Menú QR Online</caption>
        <thead>
          <tr className="bg-white border-b-2 border-slate-200 sticky top-0 z-20">
            <th
              scope="col"
              className="py-4 pl-4 pr-2 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider sticky left-0 bg-white z-30 min-w-[200px] border-r border-slate-100"
            >
              Funcionalidad
            </th>
            {(['LITE', 'PRO', 'PREMIUM'] as const).map((label) => (
              <th
                key={label}
                scope="col"
                className={cn(
                  'py-4 px-3 text-center text-sm font-bold w-28',
                  PLAN_HEADER_COLORS[label],
                )}
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
          <tbody>
            {features.map((feature, idx) => (
              <FeatureRow
                key={feature.key}
                feature={feature}
                rowIndex={idx}
                proState={proState}
              />
            ))}
          </tbody>
        </table>
      </div>
  );
}

// ---------------------------------------------------------------------------
// Mobile view — same dynamic sort, plan selector doubles as sort control
// ---------------------------------------------------------------------------

const MOBILE_PLAN_LABELS: Record<'lite' | 'pro' | 'premium', string> = {
  lite: 'LITE',
  pro: 'PRO',
  premium: 'PREMIUM',
};

function MobileView({ proState }: { proState: QrProState }) {
  // selectedPlan drives both view (which plan's cells to bucket) and sort order
  const [selectedPlan, setSelectedPlan] = useState<'lite' | 'pro' | 'premium'>('pro');
  const features = sortedFeatures(selectedPlan, proState);

  const includedBucket = features.filter((f) => {
    const s = resolveCellStatus(f, selectedPlan, proState);
    return s === 'included' || s === 'included_via_addon';
  });
  const addonBucket = features.filter((f) => {
    const s = resolveCellStatus(f, selectedPlan, proState);
    return s === 'addon_available' || s === 'pro_chooseable';
  });
  const notIncludedBucket = features.filter(
    (f) => resolveCellStatus(f, selectedPlan, proState) === 'not_included',
  );

  const renderItem = (feature: QrFeatureEntry) => {
    const status = resolveCellStatus(feature, selectedPlan, proState);
    return (
      <li key={feature.key} className="px-4 py-3 flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-800">{feature.title}</p>
          <p className="text-xs text-slate-500 mt-0.5">{feature.description}</p>
          {status === 'pro_chooseable' && feature.conditionalNote && (
            <p className="text-xs text-amber-700 mt-1 font-medium">{feature.conditionalNote}</p>
          )}
        </div>
        <div className="flex-shrink-0 mt-0.5">
          <PlanMark status={status} conditionalNote={feature.conditionalNote} />
          <span className="sr-only">{STATUS_ARIA[status]}</span>
        </div>
      </li>
    );
  };

  return (
    <div>
      <label htmlFor="qr-mobile-plan" className="block text-sm font-medium text-slate-700 mb-1.5">
        Ver detalles de:
      </label>
      <select
        id="qr-mobile-plan"
        value={selectedPlan}
        onChange={(e) => setSelectedPlan(e.target.value as 'lite' | 'pro' | 'premium')}
        className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white mb-4"
      >
        {(['lite', 'pro', 'premium'] as const).map((p) => (
          <option key={p} value={p}>
            {MOBILE_PLAN_LABELS[p]}
          </option>
        ))}
      </select>

      {includedBucket.length > 0 && (
        <div className="rounded-xl border border-slate-200 overflow-hidden mb-3">
          <div className="bg-slate-50 px-4 py-2 border-b border-slate-100">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Incluido en {MOBILE_PLAN_LABELS[selectedPlan]}
            </p>
          </div>
          <ul role="list" className="divide-y divide-slate-100">{includedBucket.map(renderItem)}</ul>
        </div>
      )}

      {addonBucket.length > 0 && (
        <div className="rounded-xl border border-amber-200 overflow-hidden mb-3">
          <div className="bg-amber-50 px-4 py-2 border-b border-amber-100">
            <p className="text-xs font-semibold uppercase tracking-wider text-amber-700">
              Add-on / A elegir
            </p>
          </div>
          <ul role="list" className="divide-y divide-slate-100">{addonBucket.map(renderItem)}</ul>
        </div>
      )}

      {notIncludedBucket.length > 0 && (
        <div className="rounded-xl border border-slate-200 overflow-hidden">
          <div className="bg-slate-50 px-4 py-2 border-b border-slate-100">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              No incluido en {MOBILE_PLAN_LABELS[selectedPlan]}
            </p>
          </div>
          <ul role="list" className="divide-y divide-slate-100">{notIncludedBucket.map(renderItem)}</ul>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add-ons block
// ---------------------------------------------------------------------------

function AddonsBlock() {
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
      <h3 className="text-sm font-bold text-amber-800 uppercase tracking-wider mb-3">
        Add-ons disponibles (solo plan PRO)
      </h3>
      <ul role="list" className="space-y-3">
        {QR_ADDONS.map((addon) => (
          <li key={addon.code} className="flex flex-col sm:flex-row sm:items-start sm:gap-4">
            <div className="flex-1">
              <p className="text-sm font-semibold text-slate-800">{addon.title}</p>
              <p className="text-xs text-slate-500 mt-0.5">{addon.description}</p>
            </div>
            <div className="mt-1 sm:mt-0 text-right shrink-0">
              <span className="text-sm font-bold text-amber-700">{addon.pricing.monthly}</span>
              <span className="text-xs text-slate-500 ml-1">· {addon.pricing.yearly}</span>
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-amber-700">
        Ambos módulos están incluidos sin costo adicional en Premium.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pro module info block
// ---------------------------------------------------------------------------

function ProModuleInfoBlock() {
  return (
    <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-5">
      <h3 className="text-sm font-bold text-indigo-800 uppercase tracking-wider mb-3 flex items-center gap-2">
        <Zap className="w-4 h-4" aria-hidden="true" />
        Módulos elegibles en PRO
      </h3>
      <ul role="list" className="space-y-3">
        {PRO_MODULE_OPTIONS.map((opt) => (
          <li key={opt.value} className="flex flex-col">
            <p className="text-sm font-semibold text-slate-800">{opt.label}</p>
            <p className="text-xs text-slate-500 mt-0.5">{opt.description}</p>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-indigo-700">
        Elegís 1 módulo incluido en el precio base de PRO. El segundo módulo queda disponible como
        add-on a precio reducido.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Modules count comparison block
// ---------------------------------------------------------------------------

function ModulesCountBlock() {
  const entries: { plan: string; count: string; color: string }[] = [
    { plan: 'LITE', count: '0 módulos de engagement', color: 'text-slate-500' },
    { plan: 'PRO', count: '1 incluido + 1 add-on', color: 'text-indigo-700' },
    { plan: 'PREMIUM', count: '2 módulos incluidos', color: 'text-violet-700' },
  ];
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
      <h3 className="text-sm font-bold text-slate-600 uppercase tracking-wider mb-3">
        Módulos de engagement incluidos
      </h3>
      <ul role="list" className="space-y-2">
        {entries.map(({ plan, count, color }) => (
          <li key={plan} className="flex items-center gap-3 text-sm">
            <span className="font-mono bg-slate-200 px-2 py-0.5 rounded text-xs font-bold text-slate-700 w-20 text-center shrink-0">
              {plan}
            </span>
            <span className={cn('font-medium', color)}>{count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main exported component
// ---------------------------------------------------------------------------

interface MenuQrComparisonTableProps {
  proState: QrProState;
}

export function MenuQrComparisonTable({ proState }: MenuQrComparisonTableProps) {
  return (
    <section
      aria-labelledby="qr-comparison-heading"
      className="mt-16 border-t border-slate-200 pt-14"
    >
      <div className="text-center mb-10">
        <h2
          id="qr-comparison-heading"
          className="text-2xl md:text-3xl font-display font-bold text-slate-900"
        >
          Compará planes en detalle
        </h2>
        <p className="mt-2 text-slate-500 text-base max-w-xl mx-auto">
          Reseñas y Propinas están disponibles en PRO — elegís cuál incluir y el otro queda como
          add-on. El orden de la tabla se actualiza según tu selección.
        </p>
      </div>

      {/* Legend */}
      <div className="mb-8 flex justify-center">
        <div className="bg-slate-50 rounded-xl border border-slate-200 px-5 py-3 inline-block">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
            Referencias
          </p>
          <Legend />
        </div>
      </div>

      {/* Desktop table */}
      <div className="hidden md:block mb-6">
        <p className="text-xs text-slate-400 mb-2 flex items-center gap-1">
          <Info className="w-3 h-3" aria-hidden="true" />
          Hacé clic en el ícono{' '}
          <Info className="w-3 h-3 inline" aria-hidden="true" /> para ver la descripción de cada
          funcionalidad.
        </p>
        <DesktopTable proState={proState} />
      </div>

      {/* Mobile view */}
      <div className="md:hidden mb-6">
        <MobileView proState={proState} />
      </div>

      {/* Info blocks */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-8">
        <ProModuleInfoBlock />
        <AddonsBlock />
        <ModulesCountBlock />
      </div>

      <p className="mt-6 text-xs text-center text-slate-400">
        Precios en ARS sin IVA. Podés cancelar o cambiar de plan en cualquier momento.
      </p>
    </section>
  );
}
