'use client';

import { Fragment, useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import Link from 'next/link';
import type { Route } from 'next';
import { Check, Info, ArrowRight, ChevronDown, ChevronUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SiteContainer } from '@/components/layout/site-container';
import { cn } from '@/lib/utils';
import {
    GC_PLANS,
    GC_PLAN_KEY_FEATURES,
    GC_PLAN_META,
    FEATURE_CATALOG,
    PLAN_LIMITS,
    type FeatureAvailability,
    type FeatureEntry,
    type GcPlanEntry,
} from '@/features/billing/data/gestion-comercial-catalog';
import { formatPrice } from '@/lib/pricing';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const PLAN_KEYS = ['start', 'pro', 'business'] as const;
const PLAN_LABELS: Record<string, string> = { start: 'Starter', pro: 'Pro', business: 'Business' };

// Map the 13 catalog categories → 5 broader landing-page groups
type BroadGroup = 'Operación' | 'Ventas y Clientes' | 'Finanzas' | 'Reportes y Datos' | 'Control y Escala';
const CATEGORY_TO_GROUP: Record<string, BroadGroup> = {
    Productos: 'Operación',
    Inventario: 'Operación',
    Pedidos: 'Operación',
    Caja: 'Operación',
    Ventas: 'Ventas y Clientes',
    Clientes: 'Ventas y Clientes',
    Facturación: 'Finanzas',
    Tesorería: 'Finanzas',
    Reportes: 'Reportes y Datos',
    Exportación: 'Reportes y Datos',
    Auditoría: 'Reportes y Datos',
    Seguridad: 'Control y Escala',
    'Multi-sucursal': 'Control y Escala',
};
const BROAD_GROUP_ORDER: BroadGroup[] = ['Operación', 'Ventas y Clientes', 'Finanzas', 'Reportes y Datos', 'Control y Escala'];

type GestionEnterprisePlan = {
    plan: 'enterprise';
    label: string;
    description: string;
    ctaLabel: string;
    ctaHref: string;
    highlights: string[];
};

const GESTION_ENTERPRISE_PLAN: GestionEnterprisePlan = {
    plan: 'enterprise',
    label: 'Empresarial',
    description: 'Solución a medida para operaciones más complejas',
    ctaLabel: 'Hablar con MiRubro',
    ctaHref: '/contacto',
    highlights: [
        'Implementación según tu operación',
        'Procesos, permisos y configuración personalizada',
        'Acompañamiento para necesidades específicas',
        'Propuesta comercial a medida',
    ],
};

type GestionLandingPlan = GcPlanEntry | GestionEnterprisePlan;

function isGestionEnterprisePlan(plan: GestionLandingPlan): plan is GestionEnterprisePlan {
    return plan.plan === 'enterprise';
}

/** Group features by broad category, included-first within each group */
function groupedFeatures() {
    const score = (s: FeatureAvailability) =>
        s === 'included' ? 2 : s === 'addon' || s === 'custom' ? 1 : 0;
    const groups = new Map<BroadGroup, FeatureEntry[]>();
    for (const g of BROAD_GROUP_ORDER) groups.set(g, []);
    for (const f of FEATURE_CATALOG) {
        const g = CATEGORY_TO_GROUP[f.category] ?? 'Operación';
        groups.get(g)!.push(f);
    }
    // Sort within each group: more included first
    for (const [, feats] of groups) {
        feats.sort((a, b) => {
            const sumA = PLAN_KEYS.reduce((s, k) => s + score(a.availability[k]), 0);
            const sumB = PLAN_KEYS.reduce((s, k) => s + score(b.availability[k]), 0);
            return sumB - sumA;
        });
    }
    return groups;
}

// ---------------------------------------------------------------------------
// FeatureInfoTooltip — portal-based, hover/focus
// ---------------------------------------------------------------------------

function FeatureInfoTooltip({ title, description }: { title: string; description: string }) {
    const [visible, setVisible] = useState(false);
    const [pos, setPos] = useState({ top: 0, left: 0 });
    const triggerRef = useRef<HTMLButtonElement>(null);
    const WIDTH = 280;
    const GAP = 8;

    const calcPos = useCallback(() => {
        const el = triggerRef.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const spaceRight = window.innerWidth - rect.right;
        const left =
            spaceRight >= WIDTH + GAP * 2
                ? rect.right + GAP
                : rect.left - WIDTH - GAP;
        setPos({ top: rect.top + rect.height / 2 + window.scrollY, left });
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
                      style={{ position: 'absolute', top: pos.top, left: pos.left, width: WIDTH, transform: 'translateY(-50%)', zIndex: 9999 }}
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
                className="flex-shrink-0 rounded p-0.5 text-slate-400 hover:text-brand-600 hover:bg-brand-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 transition-colors"
            >
                <Info className="w-3.5 h-3.5" aria-hidden="true" />
            </button>
            {tooltipEl}
        </>
    );
}

function AvailabilityMark({ status }: { status: FeatureAvailability }) {
    if (status === 'included')
        return (
            <span className="inline-flex w-5 h-5 rounded-full bg-brand-500 items-center justify-center">
                <Check className="w-3 h-3 text-white" strokeWidth={3} />
            </span>
        );
    if (status === 'addon')
        return <span className="text-xs font-medium text-amber-600">Add-on</span>;
    if (status === 'custom')
        return <span className="text-xs font-medium text-violet-600">Custom</span>;
    return (
        <span className="inline-flex w-5 h-5 rounded-full bg-slate-200 items-center justify-center">
            <span className="w-2 h-0.5 bg-slate-400 rounded" />
        </span>
    );
}

// ---------------------------------------------------------------------------
// Plan Cards (data-driven from catalog)
// ---------------------------------------------------------------------------

function PlanCard({
    plan,
    billingPeriod,
}: {
    plan: GestionLandingPlan;
    billingPeriod: 'monthly' | 'yearly';
}) {
    if (isGestionEnterprisePlan(plan)) {
        return (
            <div className="rounded-2xl border bg-white flex flex-col h-full transition-all border-slate-200 shadow-sm hover:shadow-md">
                <div className="h-full flex flex-col p-6">
                    <div className="min-h-[24px] mb-2" />

                    <h3 className="text-2xl font-bold text-slate-900 mb-1">{plan.label}</h3>
                    <p className="text-sm text-slate-500 mb-4 min-h-[40px]">{plan.description}</p>

                    <div className="mb-5">
                        <span className="text-3xl font-bold text-slate-900">Hablemos</span>
                    </div>

                    <ul className="space-y-2 flex-1">
                        {plan.highlights.map((feat) => (
                            <li key={feat} className="flex items-start gap-2 text-sm text-slate-700">
                                <Check className="h-4 w-4 mt-0.5 text-green-500 flex-shrink-0" />
                                {feat}
                            </li>
                        ))}
                    </ul>

                    <div className="mt-6 pt-4">
                        <Button asChild size="lg" className="w-full bg-slate-100 text-slate-900 hover:bg-slate-200" variant="secondary">
                            <Link href={plan.ctaHref as Route}>
                                {plan.ctaLabel}
                                <ArrowRight className="ml-2 h-4 w-4" />
                            </Link>
                        </Button>
                    </div>
                </div>
            </div>
        );
    }

    const isRecommended = plan.isRecommended ?? false;
    const price = billingPeriod === 'monthly' ? plan.priceMonthly : plan.priceYearly;
    const meta = GC_PLAN_META[plan.plan];

    return (
        <div
            className={cn(
                'rounded-2xl border bg-white flex flex-col h-full transition-all',
                isRecommended
                    ? 'border-brand-500 ring-2 ring-brand-500 shadow-lg scale-[1.02]'
                    : 'border-slate-200 shadow-sm hover:shadow-md'
            )}
        >
            <div className="h-full flex flex-col p-6">
                {/* Badge */}
                <div className="min-h-[24px] mb-2">
                    {plan.badge && (
                        <span className="inline-block bg-brand-500 text-white text-xs font-bold px-3 py-1 rounded-full">
                            {plan.badge}
                        </span>
                    )}
                </div>

                {/* Header */}
                <h3 className="text-2xl font-bold text-slate-900 mb-1">{plan.label}</h3>
                <p className="text-sm text-slate-500 mb-4 min-h-[40px]">{plan.description}</p>

                {/* Price */}
                <div className="mb-5">
                    <span className="text-3xl font-bold text-slate-900">
                        {formatPrice(price)}
                    </span>
                    <span className="text-sm text-slate-500 ml-1.5">
                        / {billingPeriod === 'yearly' ? 'año' : 'mes'}
                    </span>
                    {billingPeriod === 'yearly' && (
                        <p className="text-green-600 text-xs font-semibold mt-1">
                            Ahorrás 20% vs mensual
                        </p>
                    )}
                </div>

                {/* Meta */}
                <div className="mb-4 pb-4 border-b border-slate-100 space-y-1.5 text-sm text-slate-600">
                    <p>🏪 {meta.branches}</p>
                    <p>👥 {meta.users}</p>
                    <p className="font-semibold text-slate-700">✨ {meta.highlight}</p>
                </div>

                {/* Key features */}
                <ul className="space-y-2 flex-1">
                    {GC_PLAN_KEY_FEATURES[plan.plan].map((feat) => (
                        <li key={feat} className="flex items-start gap-2 text-sm text-slate-700">
                            <Check className="h-4 w-4 mt-0.5 text-green-500 flex-shrink-0" />
                            {feat}
                        </li>
                    ))}
                </ul>

                {/* CTA */}
                <div className="mt-6 pt-4">
                    <Button
                        asChild
                        size="lg"
                        className={cn(
                            'w-full',
                            isRecommended
                                ? 'bg-brand-600 hover:bg-brand-500 text-white shadow-md'
                                : 'bg-slate-100 text-slate-900 hover:bg-slate-200'
                        )}
                        variant={isRecommended ? 'default' : 'secondary'}
                    >
                        <Link href={'/pricing?service=commerce' as Route}>
                            {plan.ctaLabel}
                            <ArrowRight className="ml-2 h-4 w-4" />
                        </Link>
                    </Button>
                </div>
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Comparison Table (responsive)
// ---------------------------------------------------------------------------

function ComparisonTable() {
    const groups = groupedFeatures();

    return (
        <div className="overflow-x-auto rounded-xl border border-slate-200 shadow-sm">
            <table className="min-w-full border-collapse text-sm">
                <caption className="sr-only">
                    Comparativa de funcionalidades — Gestión Comercial
                </caption>
                <thead>
                    <tr className="bg-white border-b-2 border-slate-200">
                        <th
                            scope="col"
                            className="py-4 pl-4 pr-2 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider sticky left-0 bg-white z-10 min-w-[200px] border-r border-slate-100"
                        >
                            Funcionalidad
                        </th>
                        {PLAN_KEYS.map((k) => (
                            <th
                                key={k}
                                scope="col"
                                className="py-4 px-4 text-center text-sm font-bold text-brand-700 w-28"
                            >
                                {PLAN_LABELS[k]}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {BROAD_GROUP_ORDER.map((group) => {
                        const feats = groups.get(group) ?? [];
                        if (feats.length === 0) return null;
                        return (
                            <Fragment key={group}>
                                <tr>
                                    <td
                                        colSpan={4}
                                        className="py-2.5 pl-4 text-xs font-semibold text-slate-500 bg-slate-50/80 border-t border-slate-200"
                                    >
                                        {group}
                                    </td>
                                </tr>
                                {feats.map((f, idx) => {
                                    const bg = idx % 2 !== 0 ? 'bg-slate-50/50' : 'bg-white';
                                    return (
                                        <tr key={f.key} className={cn('border-b border-slate-100', bg)}>
                                            <th
                                                scope="row"
                                                className={cn(
                                                    'py-3 pl-4 pr-2 text-left text-sm font-medium text-slate-700 sticky left-0 z-10',
                                                    bg
                                                )}
                                            >
                                                <span className="flex items-center justify-between gap-2 w-full">
                                                    <span>{f.title}</span>
                                                    <FeatureInfoTooltip title={f.title} description={f.description} />
                                                </span>
                                            </th>
                                            {PLAN_KEYS.map((k) => (
                                                <td key={k} className="py-3 px-4 text-center">
                                                    <AvailabilityMark status={f.availability[k]} />
                                                </td>
                                            ))}
                                        </tr>
                                    );
                                })}
                            </Fragment>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Mobile comparison (plan selector)
// ---------------------------------------------------------------------------

function MobileComparison() {
    const [selected, setSelected] = useState<(typeof PLAN_KEYS)[number]>('pro');
    const groups = groupedFeatures();

    return (
        <div>
            <div className="mb-4">
                <label htmlFor="gc-mobile-plan" className="block text-sm font-medium text-slate-700 mb-1.5">
                    Ver funcionalidades de:
                </label>
                <select
                    id="gc-mobile-plan"
                    value={selected}
                    onChange={(e) => setSelected(e.target.value as typeof selected)}
                    className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white"
                >
                    {PLAN_KEYS.map((k) => (
                        <option key={k} value={k}>{PLAN_LABELS[k]}</option>
                    ))}
                </select>
            </div>
            <div className="space-y-3">
                {BROAD_GROUP_ORDER.map((group) => {
                    const feats = groups.get(group) ?? [];
                    if (feats.length === 0) return null;
                    const included = feats.filter((f) => f.availability[selected] !== 'not_included');
                    const notIncl = feats.filter((f) => f.availability[selected] === 'not_included');
                    return (
                        <div key={group} className="rounded-xl border border-slate-200 overflow-hidden">
                            <div className="bg-slate-50 px-4 py-2 border-b border-slate-100">
                                <p className="text-xs font-semibold text-slate-500">{group}</p>
                            </div>
                            <ul className="divide-y divide-slate-100">
                                {included.map((f) => (
                                    <li key={f.key} className="px-4 py-3 flex items-center justify-between gap-2">
                                        <span className="text-sm text-slate-700">{f.title}</span>
                                        <AvailabilityMark status={f.availability[selected]} />
                                    </li>
                                ))}
                                {notIncl.map((f) => (
                                    <li key={f.key} className="px-4 py-3 flex items-center justify-between gap-2 opacity-50">
                                        <span className="text-sm text-slate-500">{f.title}</span>
                                        <AvailabilityMark status="not_included" />
                                    </li>
                                ))}
                            </ul>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Plan Limits
// ---------------------------------------------------------------------------

function PlanLimitsCards() {
    return (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-6">
            {PLAN_LIMITS.filter((p) => !p.isCustom).map((p) => (
                <div key={p.plan} className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
                    <p className="font-bold text-slate-900 mb-2">{p.label}</p>
                    <p className="text-slate-600"><span className="text-slate-400 mr-1">Sucursales:</span>{p.branches}</p>
                    <p className="text-slate-600 mt-1"><span className="text-slate-400 mr-1">Usuarios:</span>{p.users}</p>
                </div>
            ))}
        </div>
    );
}

// ---------------------------------------------------------------------------
// Main exported section
// ---------------------------------------------------------------------------

export function GestionPricingSection() {
    const [billingPeriod, setBillingPeriod] = useState<'monthly' | 'yearly'>('monthly');
    const [showTable, setShowTable] = useState(false);
    const landingPlans: GestionLandingPlan[] = [...GC_PLANS, GESTION_ENTERPRISE_PLAN];

    return (
        <section className="py-16 lg:py-24" id="planes-gestion">
            <SiteContainer>
                <div className="space-y-10">
                    {/* Header */}
                    <div className="text-center max-w-2xl mx-auto space-y-3">
                        <p className="text-sm font-semibold uppercase tracking-[0.25em] text-brand-600">
                            Planes
                        </p>
                        <h2 className="text-3xl font-display font-bold text-slate-900">
                            Elegí el plan para tu negocio
                        </h2>
                        <p className="text-lg text-slate-600">
                            Precios reales. Sin costos ocultos. Cancelá cuando quieras.
                        </p>
                    </div>

                    {/* Billing toggle */}
                    <div className="flex justify-center">
                        <div className="inline-flex bg-slate-100 rounded-full p-1">
                            <button
                                type="button"
                                onClick={() => setBillingPeriod('monthly')}
                                className={cn(
                                    'px-5 py-2 text-sm font-medium rounded-full transition-all',
                                    billingPeriod === 'monthly'
                                        ? 'bg-white text-slate-900 shadow-sm'
                                        : 'text-slate-500 hover:text-slate-700'
                                )}
                            >
                                Mensual
                            </button>
                            <button
                                type="button"
                                onClick={() => setBillingPeriod('yearly')}
                                className={cn(
                                    'px-5 py-2 text-sm font-medium rounded-full transition-all',
                                    billingPeriod === 'yearly'
                                        ? 'bg-white text-slate-900 shadow-sm'
                                        : 'text-slate-500 hover:text-slate-700'
                                )}
                            >
                                Anual <span className="text-green-600 font-semibold ml-1">-20%</span>
                            </button>
                        </div>
                    </div>

                    {/* Plan cards */}
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6 items-stretch max-w-6xl mx-auto">
                        {landingPlans.map((plan) => (
                            <PlanCard key={plan.plan} plan={plan} billingPeriod={billingPeriod} />
                        ))}
                    </div>

                    <p className="text-xs text-center text-slate-400">
                        Precios en pesos argentinos (ARS). Cobro a través de Mercado Pago.
                    </p>

                    {/* Toggle para tabla comparativa */}
                    <div className="text-center">
                        <button
                            type="button"
                            onClick={() => setShowTable(!showTable)}
                            className="inline-flex items-center gap-2 text-sm font-medium text-brand-600 hover:text-brand-700 transition-colors"
                        >
                            {showTable ? 'Ocultar' : 'Ver'} comparación detallada de funcionalidades
                            {showTable ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        </button>
                    </div>

                    {showTable && (
                        <div className="space-y-8 pt-4">
                            {/* Plan limits */}
                            <PlanLimitsCards />

                            {/* Desktop table */}
                            <div className="hidden md:block">
                                <ComparisonTable />
                            </div>

                            {/* Mobile view */}
                            <div className="md:hidden">
                                <MobileComparison />
                            </div>

                            {/* Legend */}
                            <div className="flex justify-center">
                                <div className="inline-flex gap-6 bg-slate-50 rounded-xl border border-slate-200 px-5 py-3">
                                    {([
                                        ['included', 'Incluido'],
                                        ['not_included', 'No incluido'],
                                        ['addon', 'Add-on'],
                                    ] as const).map(([status, label]) => (
                                        <span key={status} className="flex items-center gap-2 text-xs text-slate-600">
                                            <AvailabilityMark status={status} />
                                            {label}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </SiteContainer>
        </section>
    );
}
