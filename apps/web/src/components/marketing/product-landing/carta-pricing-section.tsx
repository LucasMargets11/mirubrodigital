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
    QR_PLANS,
    QR_FEATURE_CATALOG,
    QR_ADDONS,
    type QrPlanEntry,
    type QrFeatureAvailability,
} from '@/features/billing/data/menu-qr-catalog';
import { formatPrice } from '@/lib/pricing';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const PLAN_KEYS = ['lite', 'pro', 'premium'] as const;
const PLAN_LABELS: Record<string, string> = { lite: 'Lite', pro: 'Pro', premium: 'Premium' };

// Map 6 QR categories → 3 broader groups
type QrBroadGroup = 'Tu Carta' | 'Análitica y Datos' | 'Engagement y Escala';
const QR_CATEGORY_TO_GROUP: Record<string, QrBroadGroup> = {
    'Carta Digital': 'Tu Carta',
    'Branding': 'Tu Carta',
    'Imágenes': 'Tu Carta',
    'Analítica': 'Análitica y Datos',
    'Engagement': 'Engagement y Escala',
    'Infraestructura': 'Engagement y Escala',
};
const QR_BROAD_GROUP_ORDER: QrBroadGroup[] = ['Tu Carta', 'Análitica y Datos', 'Engagement y Escala'];

/** Group features by broad category, included-first within each group */
function groupedQrFeatures() {
    const score = (s: QrFeatureAvailability) =>
        s === 'included' ? 3 : s === 'conditional' ? 2 : s === 'addon' ? 1 : 0;
    const groups = new Map<QrBroadGroup, typeof QR_FEATURE_CATALOG>();
    for (const g of QR_BROAD_GROUP_ORDER) groups.set(g, []);
    for (const f of QR_FEATURE_CATALOG) {
        const g = QR_CATEGORY_TO_GROUP[f.category] ?? 'Tu Carta';
        groups.get(g)!.push(f);
    }
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

const KEY_FEATURES: Record<string, string[]> = {
    lite: [
        'Carta online con QR',
        'Categorías y productos ilimitados',
        'Branding básico (logo y colores)',
        'URL pública única',
        'Analítica básica',
    ],
    pro: [
        'Todo de Lite',
        'Fotos HD por producto',
        'Analítica avanzada',
        '1 módulo de engagement a elección',
        'Add-ons disponibles',
    ],
    premium: [
        'Todo de Pro',
        'Reseñas + Propinas incluidas',
        'Propinas dinámicas (MP OAuth)',
        'Dominio personalizado',
        'Multi-sucursal',
    ],
};

function AvailabilityMark({ status }: { status: QrFeatureAvailability }) {
    if (status === 'included')
        return (
            <span className="inline-flex w-5 h-5 rounded-full bg-brand-500 items-center justify-center">
                <Check className="w-3 h-3 text-white" strokeWidth={3} />
            </span>
        );
    if (status === 'addon')
        return <span className="text-xs font-medium text-amber-600">Add-on</span>;
    if (status === 'conditional')
        return <span className="text-xs font-medium text-violet-600">Elegible</span>;
    if (status === 'custom')
        return <span className="text-xs font-medium text-violet-600">Custom</span>;
    return (
        <span className="inline-flex w-5 h-5 rounded-full bg-slate-200 items-center justify-center">
            <span className="w-2 h-0.5 bg-slate-400 rounded" />
        </span>
    );
}

// ---------------------------------------------------------------------------
// Plan Card
// ---------------------------------------------------------------------------

function PlanCard({
    plan,
    billingPeriod,
}: {
    plan: QrPlanEntry;
    billingPeriod: 'monthly' | 'yearly';
}) {
    const isRecommended = plan.isRecommended ?? false;
    const price = billingPeriod === 'monthly' ? plan.priceMonthly : plan.priceYearly;

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

                {/* Key features */}
                <ul className="space-y-2 flex-1 mb-6 border-t border-slate-100 pt-4">
                    {KEY_FEATURES[plan.plan].map((feat) => (
                        <li key={feat} className="flex items-start gap-2 text-sm text-slate-700">
                            <Check className="h-4 w-4 mt-0.5 text-green-500 flex-shrink-0" />
                            {feat}
                        </li>
                    ))}
                </ul>

                {/* CTA */}
                <div className="pt-4">
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
                        <Link href={'/pricing?service=menu_qr' as Route}>
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
// Comparison Table (desktop)
// ---------------------------------------------------------------------------

function ComparisonTable() {
    const groups = groupedQrFeatures();

    return (
        <div className="overflow-x-auto rounded-xl border border-slate-200 shadow-sm">
            <table className="min-w-full border-collapse text-sm">
                <caption className="sr-only">
                    Comparativa de funcionalidades — Carta Online
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
                    {QR_BROAD_GROUP_ORDER.map((group) => {
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
// Mobile comparison
// ---------------------------------------------------------------------------

function MobileComparison() {
    const [selected, setSelected] = useState<(typeof PLAN_KEYS)[number]>('pro');
    const groups = groupedQrFeatures();

    return (
        <div>
            <div className="mb-4">
                <label htmlFor="qr-mobile-plan" className="block text-sm font-medium text-slate-700 mb-1.5">
                    Ver funcionalidades de:
                </label>
                <select
                    id="qr-mobile-plan"
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
                {QR_BROAD_GROUP_ORDER.map((group) => {
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
// Add-ons block
// ---------------------------------------------------------------------------

function AddonsBlock() {
    return (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
            <h4 className="text-sm font-bold text-amber-900 mb-3">Add-ons (solo plan Pro)</h4>
            <p className="text-xs text-amber-700 mb-3">
                En Pro elegís 1 módulo de engagement incluido. El otro queda disponible como add-on.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {QR_ADDONS.map((a) => (
                    <div key={a.code} className="bg-white rounded-lg border border-amber-100 p-3">
                        <p className="font-semibold text-sm text-slate-900">{a.title}</p>
                        <p className="text-xs text-slate-500 mt-0.5">{a.description}</p>
                        <p className="text-xs font-medium text-amber-700 mt-1.5">{a.pricing.monthly}</p>
                    </div>
                ))}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Main exported section
// ---------------------------------------------------------------------------

export function CartaPricingSection() {
    const [billingPeriod, setBillingPeriod] = useState<'monthly' | 'yearly'>('monthly');
    const [showTable, setShowTable] = useState(false);

    return (
        <section className="py-16 lg:py-24" id="planes-carta">
            <SiteContainer>
                <div className="space-y-10">
                    {/* Header */}
                    <div className="text-center max-w-2xl mx-auto space-y-3">
                        <p className="text-sm font-semibold uppercase tracking-[0.25em] text-brand-600">
                            Planes
                        </p>
                        <h2 className="text-3xl font-display font-bold text-slate-900">
                            Elegí cómo publicar tu carta
                        </h2>
                        <p className="text-lg text-slate-600">
                            Precios reales. Sin comisiones. Cancelá cuando quieras.
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
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-stretch max-w-4xl mx-auto">
                        {QR_PLANS.map((plan) => (
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
                            {/* Desktop table */}
                            <div className="hidden md:block">
                                <ComparisonTable />
                            </div>

                            {/* Mobile view */}
                            <div className="md:hidden">
                                <MobileComparison />
                            </div>

                            {/* Add-ons */}
                            <AddonsBlock />

                            {/* Legend */}
                            <div className="flex justify-center">
                                <div className="inline-flex gap-6 bg-slate-50 rounded-xl border border-slate-200 px-5 py-3">
                                    {([
                                        ['included', 'Incluido'],
                                        ['not_included', 'No incluido'],
                                        ['conditional', 'Elegible en PRO'],
                                        ['addon', 'Add-on'],
                                    ] as const).map(([status, label]) => (
                                        <span key={status} className="flex items-center gap-2 text-xs text-slate-600">
                                            <AvailabilityMark status={status as QrFeatureAvailability} />
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
