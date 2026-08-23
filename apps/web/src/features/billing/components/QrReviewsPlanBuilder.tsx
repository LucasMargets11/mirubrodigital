'use client';

import { REVIEWS_BASE, REVIEWS_PRO, formatPrice } from '@/lib/pricing';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface QrReviewsSubscribeConfig {
    planCode: string;
}

interface QrReviewsPlanEntry {
    plan: string;
    label: string;
    description: string;
    priceMonthly: number;
    priceYearly: number;
    badge?: string;
    isRecommended?: boolean;
    ctaLabel: string;
}

interface QrReviewsPlanBuilderProps {
    billingPeriod: 'monthly' | 'yearly';
    onSubscribe: (config: QrReviewsSubscribeConfig) => void;
}

// ---------------------------------------------------------------------------
// Plan data — derived from canonical lib/pricing
// ---------------------------------------------------------------------------

const QR_REVIEWS_PLANS: QrReviewsPlanEntry[] = [
    {
        plan: REVIEWS_BASE.code,
        label: REVIEWS_BASE.name,
        description: 'Filtrá qué llega a Google y empezá a recibir feedback privado.',
        priceMonthly: REVIEWS_BASE.priceMonthly,
        priceYearly: REVIEWS_BASE.priceYearly,
        ctaLabel: 'Activar Reseñas Base',
    },
    {
        plan: REVIEWS_PRO.code,
        label: REVIEWS_PRO.name,
        description: 'Gestioná tu reputación con métricas, estados y carteles profesionales.',
        priceMonthly: REVIEWS_PRO.priceMonthly,
        priceYearly: REVIEWS_PRO.priceYearly,
        badge: '⭐ Recomendado',
        isRecommended: true,
        ctaLabel: 'Activar Reseñas Pro',
    },
];

const PLAN_KEY_FEATURES: Record<string, string[]> = {
    [REVIEWS_BASE.code]: [
        'QR listo para compartir y descargar',
        'Redirección directa a Google',
        'Filtro inteligente por calificación',
        'Feedback privado básico',
    ],
    [REVIEWS_PRO.code]: [
        'Todo lo de Base',
        'Analytics avanzadas',
        'Métricas de conversión',
        'Estados de gestión avanzados',
        'Carteles profesionales imprimibles',
        'Personalización avanzada',
    ],
};

const PLAN_META: Record<string, { highlight: string }> = {
    [REVIEWS_BASE.code]: { highlight: 'Filtro inteligente + feedback privado' },
    [REVIEWS_PRO.code]: { highlight: 'Analytics, métricas y carteles profesionales' },
};

// ---------------------------------------------------------------------------
// Individual plan card — same structure/classes as GC & MenuQr
// ---------------------------------------------------------------------------

function PlanCard({
    plan,
    onSubscribe,
}: {
    plan: QrReviewsPlanEntry;
    onSubscribe: (p: QrReviewsPlanEntry) => void;
}) {
    const isRecommended = plan.isRecommended ?? false;
    const price = plan.priceMonthly;

    return (
        <div
            className={`h-full border rounded-2xl bg-white shadow-sm hover:shadow-lg transition-all ${
                isRecommended
                    ? 'border-brand-500 ring-2 ring-brand-500 scale-[1.02]'
                    : 'border-slate-200'
            }`}
        >
            <div className="h-full flex flex-col p-6">
                {/* Badge — espacio reservado */}
                <div className="min-h-[20px] mb-2">
                    {plan.badge && (
                        <span className="inline-block bg-brand-500 text-white text-xs font-bold px-3 py-1 rounded-full shadow-md">
                            {plan.badge}
                        </span>
                    )}
                </div>

                {/* Header */}
                <div className="mb-4">
                    <h3 className="text-2xl font-bold mb-2 text-slate-900">{plan.label}</h3>
                    <p className="text-slate-600 text-sm min-h-[40px]">{plan.description}</p>
                </div>

                {/* Precio */}
                <div className="mb-6">
                    <div className="flex items-baseline">
                        <span className="text-4xl font-bold text-slate-900">
                            {formatPrice(price)}
                        </span>
                        <span className="text-slate-500 text-sm ml-2">
                            / mes
                        </span>
                    </div>
                </div>

                {/* Meta bullets */}
                <div className="mb-4 pb-4 border-b border-slate-100">
                    <div className="space-y-2 text-sm">
                        <div className="flex items-center text-slate-700 font-semibold">
                            <span className="mr-2 text-brand-500">✨</span>
                            <span>{PLAN_META[plan.plan].highlight}</span>
                        </div>
                    </div>
                </div>

                {/* Checklist de features */}
                <ul className="space-y-2 flex-1">
                    {PLAN_KEY_FEATURES[plan.plan].map((feature) => (
                        <li key={feature} className="flex items-start text-sm text-slate-700">
                            <span className="mr-2 text-green-500 font-bold">✓</span>
                            <span>{feature}</span>
                        </li>
                    ))}
                </ul>

                {/* CTA — alineado al fondo */}
                <div className="mt-auto pt-6">
                    <button
                        type="button"
                        onClick={() => onSubscribe(plan)}
                        className={`w-full py-3 px-4 rounded-lg font-semibold transition-all ${
                            isRecommended
                                ? 'bg-brand-600 text-white hover:bg-brand-700 shadow-md'
                                : 'bg-slate-100 text-slate-900 hover:bg-slate-200'
                        }`}
                    >
                        {plan.ctaLabel}
                    </button>
                </div>
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function QrReviewsPlanBuilder({ billingPeriod: _billingPeriod, onSubscribe }: QrReviewsPlanBuilderProps) {
    const handleSubscribe = (plan: QrReviewsPlanEntry) => {
        onSubscribe({ planCode: plan.plan });
    };

    return (
        <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-stretch max-w-3xl mx-auto">
                {QR_REVIEWS_PLANS.map((plan) => (
                    <PlanCard
                        key={plan.plan}
                        plan={plan}
                        onSubscribe={handleSubscribe}
                    />
                ))}
            </div>
            <p className="mt-6 text-xs text-center text-slate-400">
                Precios expresados en pesos argentinos (ARS). Cobro a través de Mercado Pago.
            </p>
        </>
    );
}
