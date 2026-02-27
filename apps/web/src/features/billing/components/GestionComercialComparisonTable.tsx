'use client';

import { Fragment, useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Check, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  FEATURE_CATALOG,
  PLAN_LIMITS,
  ADDONS,
  EXTRAS,
  LEGACY_PLANS,
  type FeatureAvailability,
  type FeatureEntry,
} from '../data/gestion-comercial-catalog';

// ---------------------------------------------------------------------------
// Sort helper — features with broader plan coverage come first
// ---------------------------------------------------------------------------

function availabilityScore(a: FeatureAvailability): number {
  if (a === 'included') return 3;
  if (a === 'addon') return 2;
  return 0;
}

function featureSortScore(f: FeatureEntry): number {
  return (
    availabilityScore(f.availability.start) +
    availabilityScore(f.availability.pro) +
    availabilityScore(f.availability.business)
  );
}

const SORTED_FEATURES = [...FEATURE_CATALOG].sort(
  (a, b) => featureSortScore(b) - featureSortScore(a)
);

// Index of first feature that is only available in business/enterprise (score < 6)
const SECONDARY_START_INDEX = SORTED_FEATURES.findIndex((f) => featureSortScore(f) < 6);

// ---------------------------------------------------------------------------
// FeatureInfoTooltip — portal-based, keyboard-accessible, no-layout-shift
// ---------------------------------------------------------------------------

interface TooltipPos { top: number; left: number; placement: 'right' | 'left' }

function FeatureInfoTooltip({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  const [visible, setVisible] = useState(false);
  const [pos, setPos] = useState<TooltipPos>({ top: 0, left: 0, placement: 'right' });
  const triggerRef = useRef<HTMLButtonElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const TOOLTIP_WIDTH = 300;
  const GAP = 8;

  const calcPos = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const spaceRight = window.innerWidth - rect.right;
    const placement: 'right' | 'left' = spaceRight >= TOOLTIP_WIDTH + GAP * 2 ? 'right' : 'left';
    const left =
      placement === 'right'
        ? rect.right + GAP
        : rect.left - TOOLTIP_WIDTH - GAP;
    const top = rect.top + rect.height / 2 + window.scrollY;
    setPos({ top, left, placement });
  }, []);

  const show = useCallback(() => { calcPos(); setVisible(true); }, [calcPos]);
  const hide = useCallback(() => setVisible(false), []);

  // Close on Esc
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
            ref={tooltipRef}
            role="tooltip"
            id={`tip-${title.replace(/\s+/g, '-').toLowerCase()}`}
            style={{
              position: 'absolute',
              top: pos.top,
              left: pos.left,
              width: TOOLTIP_WIDTH,
              transform: 'translateY(-50%)',
              zIndex: 9999,
            }}
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
        aria-describedby={`tip-${title.replace(/\s+/g, '-').toLowerCase()}`}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        className="flex-shrink-0 rounded p-0.5 text-slate-400 hover:text-brand-600 hover:bg-brand-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 transition-colors"
      >
        <Info className="w-3.5 h-3.5" aria-hidden="true" />
      </button>
      {tooltipEl}
    </>
  );
}

// ---------------------------------------------------------------------------
// Status aria labels (for sr-only)
// ---------------------------------------------------------------------------

const STATUS_ARIA: Record<FeatureAvailability, string> = {
  included: 'Incluido',
  addon: 'Disponible como add-on',
  not_included: 'No incluido',
  custom: 'Custom / ilimitado (Enterprise)',
};

// ---------------------------------------------------------------------------
// PlanMark — circle-check icon for included/not_included;
//            text label for addon/custom
// ---------------------------------------------------------------------------

function PlanMark({ status }: { status: FeatureAvailability }) {
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

  if (status === 'not_included') {
    return (
      <span
        aria-hidden="true"
        className="inline-flex w-[22px] h-[22px] rounded-full bg-slate-300 items-center justify-center flex-shrink-0"
      >
        <Check className="w-3.5 h-3.5 text-slate-100" strokeWidth={2.5} />
      </span>
    );
  }

  if (status === 'addon') {
    return (
      <span aria-hidden="true" className="text-xs font-medium text-slate-500">
        Add-on
      </span>
    );
  }

  // custom
  return (
    <span aria-hidden="true" className="text-xs font-medium text-slate-500">
      Custom
    </span>
  );
}

// ---------------------------------------------------------------------------
// Subcomponents
// ---------------------------------------------------------------------------

const LEGEND_ENTRIES: { status: FeatureAvailability; label: string }[] = [
  { status: 'included', label: 'Incluido' },
  { status: 'not_included', label: 'No incluido' },
  { status: 'addon', label: 'Add-on' },
  { status: 'custom', label: 'Custom (Enterprise)' },
];

function Legend() {
  return (
    <div
      role="note"
      aria-label="Referencias de la tabla"
      className="flex flex-wrap gap-x-6 gap-y-2"
    >
      {LEGEND_ENTRIES.map(({ status, label }) => (
        <span key={status} className="flex items-center gap-2 text-xs text-slate-600">
          <PlanMark status={status} />
          <span>{label}</span>
        </span>
      ))}
    </div>
  );
}

// Plan limits mini cards
function PlanLimitsBlock() {
  return (
    <div className="mb-8">
      <h3 className="text-base font-semibold text-slate-800 mb-3">Límites por plan</h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {PLAN_LIMITS.map((p) => (
          <div
            key={p.plan}
            className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm"
          >
            <p className="font-bold text-slate-900 mb-2">{p.label}</p>
            <p className="text-slate-600">
              <span className="text-slate-400 font-medium mr-1">Sucursales:</span>
              {p.branches}
            </p>
            <p className="text-slate-600 mt-1">
              <span className="text-slate-400 font-medium mr-1">Usuarios:</span>
              {p.users}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

// Single availability cell
function AvailabilityCell({
  availability,
  featureTitle,
  planLabel,
  rowBg,
}: {
  availability: FeatureAvailability;
  featureTitle: string;
  planLabel: string;
  rowBg: string;
}) {
  return (
    <td className={cn('py-3 px-3 text-center align-middle', rowBg)} role="cell">
      <PlanMark status={availability} />
      <span className="sr-only">
        {STATUS_ARIA[availability]} en {planLabel} para {featureTitle}
      </span>
    </td>
  );
}

const PLAN_LABELS: Record<string, string> = {
  start: 'START',
  pro: 'PRO',
  business: 'BUSINESS',
  enterprise: 'ENTERPRISE',
};

// Feature row — static, no expand/collapse
function FeatureRow({ feature, rowIndex }: { feature: FeatureEntry; rowIndex: number }) {
  const isOdd = rowIndex % 2 !== 0;
  const rowBg = isOdd ? 'bg-slate-50' : 'bg-white';
  const hoverBg = 'hover:bg-slate-100/60';

  return (
    <tr className={cn('border-b border-slate-100 transition-colors', rowBg, hoverBg)}>
      {/* Feature name (sticky on desktop) */}
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
      {/* Availability cells */}
      {(['start', 'pro', 'business', 'enterprise'] as const).map((plan) => (
        <AvailabilityCell
          key={plan}
          availability={feature.availability[plan]}
          featureTitle={feature.title}
          planLabel={PLAN_LABELS[plan]}
          rowBg={rowBg}
        />
      ))}
    </tr>
  );
}

// Divider row between primary and secondary feature groups
function DividerRow({ label }: { label: string }) {
  return (
    <tr role="row" aria-hidden="true">
      <td
        colSpan={5}
        className="py-1.5 pl-4 text-[11px] font-semibold uppercase tracking-widest text-slate-400 bg-slate-50 border-t-2 border-slate-200"
      >
        {label}
      </td>
    </tr>
  );
}

// Desktop comparison table
function DesktopTable() {
  const headers = ['START', 'PRO', 'BUSINESS', 'ENTERPRISE'];

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 shadow-sm">
      <table className="min-w-full border-collapse text-sm" role="table">
        <caption className="sr-only">
          Comparativa completa de funcionalidades por plan de Gestión Comercial
        </caption>
        <thead>
          <tr className="bg-white border-b-2 border-slate-200 sticky top-0 z-20">
            <th
              scope="col"
              className="py-4 pl-4 pr-2 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider sticky left-0 bg-white z-30 min-w-[200px] border-r border-slate-100"
            >
              Funcionalidad
            </th>
            {headers.map((h, i) => (
              <th
                key={h}
                scope="col"
                className={cn(
                  'py-4 px-3 text-center text-sm font-bold w-28',
                  i === 3 ? 'text-violet-700' : i === 0 ? 'text-slate-700' : 'text-brand-700'
                )}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {SORTED_FEATURES.map((feature, idx) => (
            <Fragment key={feature.key}>
              {idx === SECONDARY_START_INDEX && (
                <DividerRow label="Exclusivo BUSINESS y ENTERPRISE" />
              )}
              <FeatureRow feature={feature} rowIndex={idx} />
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mobile: plan selector + feature list
// ---------------------------------------------------------------------------

type MobilePlan = 'start' | 'pro' | 'business' | 'enterprise';

const MOBILE_PLAN_LABELS: Record<MobilePlan, string> = {
  start: 'START',
  pro: 'PRO',
  business: 'BUSINESS',
  enterprise: 'ENTERPRISE',
};

function MobileView() {
  const [selectedPlan, setSelectedPlan] = useState<MobilePlan>('pro');

  const included = SORTED_FEATURES.filter(
    (f) => f.availability[selectedPlan] === 'included' || f.availability[selectedPlan] === 'addon'
  );
  const notIncluded = SORTED_FEATURES.filter(
    (f) => f.availability[selectedPlan] === 'not_included' || f.availability[selectedPlan] === 'custom'
  );

  const renderFeatureItem = (feature: FeatureEntry) => {
    const avail = feature.availability[selectedPlan];
    return (
      <li key={feature.key} className="px-4 py-3 flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-800">{feature.title}</p>
          <p className="text-xs text-slate-500 mt-0.5">{feature.description}</p>
        </div>
        <div className="flex-shrink-0 mt-0.5">
          <PlanMark status={avail} />
          <span className="sr-only">{STATUS_ARIA[avail]} en {MOBILE_PLAN_LABELS[selectedPlan]}</span>
        </div>
      </li>
    );
  };

  return (
    <div>
      {/* Plan selector */}
      <div className="mb-4">
        <label
          htmlFor="mobile-plan-select"
          className="block text-sm font-medium text-slate-700 mb-1.5"
        >
          Ver detalles de:
        </label>
        <select
          id="mobile-plan-select"
          value={selectedPlan}
          onChange={(e) => setSelectedPlan(e.target.value as MobilePlan)}
          className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white"
        >
          {(Object.entries(MOBILE_PLAN_LABELS) as [MobilePlan, string][]).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {/* Included features */}
      {included.length > 0 && (
        <div className="rounded-xl border border-slate-200 overflow-hidden mb-3">
          <div className="bg-slate-50 px-4 py-2 border-b border-slate-100">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Incluido en {MOBILE_PLAN_LABELS[selectedPlan]}
            </p>
          </div>
          <ul role="list" className="divide-y divide-slate-100">
            {included.map(renderFeatureItem)}
          </ul>
        </div>
      )}

      {/* Not included features */}
      {notIncluded.length > 0 && (
        <div className="rounded-xl border border-slate-200 overflow-hidden">
          <div className="bg-slate-50 px-4 py-2 border-b border-slate-100">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              No incluido en {MOBILE_PLAN_LABELS[selectedPlan]}
            </p>
          </div>
          <ul role="list" className="divide-y divide-slate-100">
            {notIncluded.map(renderFeatureItem)}
          </ul>
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
        Add-ons disponibles (plan START)
      </h3>
      <ul role="list" className="space-y-3">
        {ADDONS.map((addon) => (
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
        Estos módulos están incluidos sin costo adicional en PRO, BUSINESS y ENTERPRISE.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Extras block
// ---------------------------------------------------------------------------

function ExtrasBlock() {
  return (
    <div className="rounded-xl border border-brand-200 bg-brand-50 p-5">
      <h3 className="text-sm font-bold text-brand-800 uppercase tracking-wider mb-3">
        Extras disponibles (PRO y BUSINESS)
      </h3>
      <ul role="list" className="space-y-3">
        {EXTRAS.map((extra) => (
          <li key={extra.code} className="flex flex-col sm:flex-row sm:items-center sm:gap-4">
            <p className="flex-1 text-sm font-semibold text-slate-800">{extra.title}</p>
            <div className="mt-1 sm:mt-0 text-right shrink-0">
              <span className="text-sm font-bold text-brand-700">{extra.pricing.monthly}</span>
              <span className="text-xs text-slate-500 ml-1">· {extra.pricing.yearly}</span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Legacy mapping block
// ---------------------------------------------------------------------------

function LegacyBlock() {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
      <h3 className="text-sm font-bold text-slate-600 uppercase tracking-wider mb-3">
        Planes legacy — equivalencias
      </h3>
      <ul role="list" className="space-y-1.5">
        {LEGACY_PLANS.map((lp) => (
          <li key={lp.legacyCode} className="text-sm text-slate-600">
            <span className="font-mono bg-slate-200 px-1.5 py-0.5 rounded text-xs mr-2">
              {lp.legacyCode}
            </span>
            <span className="text-slate-400 mr-2">→</span>
            <span className="font-semibold text-slate-800">{lp.mapsToLabel}</span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-slate-500">
        Si tenés un plan legacy, tu acceso equivale al plan indicado. Podés migrar en cualquier
        momento desde la configuración de suscripción.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main exported component
// ---------------------------------------------------------------------------

export function GestionComercialComparisonTable() {
  return (
    <section
      aria-labelledby="comparison-table-heading"
      className="mt-16 border-t border-slate-200 pt-14"
    >
      {/* Desktop table */}
      <div id="comparison-table-desktop" className="hidden md:block mb-6">
        <p className="text-xs text-slate-400 mb-2 flex items-center gap-1">
          <Info className="w-3 h-3" aria-hidden="true" />
          Hacé clic en el ícono{' '}
          <Info className="w-3 h-3 inline" aria-hidden="true" /> junto a cada funcionalidad para
          ver su descripción.
        </p>
        <DesktopTable />
      </div>

      {/* Mobile view */}
      <div className="md:hidden mb-6">
        <MobileView />
      </div>

      {/* Section header */}
      <div className="text-center mt-14 mb-10">
        <h2
          id="comparison-table-heading"
          className="text-2xl md:text-3xl font-display font-bold text-slate-900"
        >
          Compará planes en detalle
        </h2>
        <p className="mt-2 text-slate-500 text-base max-w-xl mx-auto">
          Todas las funcionalidades, límites y extras en un solo lugar.
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

      {/* Plan limits */}
      <PlanLimitsBlock />

      {/* Add-ons, Extras, Legacy */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-8">
        <AddonsBlock />
        <ExtrasBlock />
        <LegacyBlock />
      </div>

      {/* Footer note */}
      <p className="mt-6 text-xs text-center text-slate-400">
        Precios expresados en USD sin impuestos. Facturación mensual o anual. Podés cancelar o
        cambiar de plan en cualquier momento.
      </p>
    </section>
  );
}
