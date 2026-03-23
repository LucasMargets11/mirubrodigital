'use client';

import {
  GC_PLANS,
  GC_PLAN_KEY_FEATURES,
  GC_PLAN_META,
  type GcPlanEntry,
} from '../data/gestion-comercial-catalog';
import { formatArsPrice } from '../data/menu-qr-catalog';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface GcSubscribeConfig {
  plan: 'start' | 'pro' | 'business';
  planCode: string;
}

interface GestionComercialPlanBuilderProps {
  billingPeriod: 'monthly' | 'yearly';
  onSubscribe: (config: GcSubscribeConfig) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function planCodeFor(plan: GcPlanEntry['plan']): string {
  return `gestion_${plan}`;
}

// ---------------------------------------------------------------------------
// Individual plan card — same structure/classes as MenuQrPlanBuilder
// ---------------------------------------------------------------------------

function PlanCard({
  plan,
  billingPeriod,
  onSubscribe,
}: {
  plan: GcPlanEntry;
  billingPeriod: 'monthly' | 'yearly';
  onSubscribe: (p: GcPlanEntry) => void;
}) {
  const isRecommended = plan.isRecommended ?? false;
  const price = billingPeriod === 'monthly' ? plan.priceMonthly : plan.priceYearly;
  const monthlyEquiv = billingPeriod === 'yearly' ? Math.round(plan.priceYearly / 12) : plan.priceMonthly;
  const meta = GC_PLAN_META[plan.plan];

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
              {formatArsPrice(billingPeriod === 'yearly' ? plan.priceYearly : plan.priceMonthly)}
            </span>
            <span className="text-slate-500 text-sm ml-2">
              / {billingPeriod === 'yearly' ? 'año' : 'mes'}
            </span>
          </div>
          {billingPeriod === 'yearly' && (
            <p className="text-green-600 text-xs font-semibold mt-1">
              Ahorrás 20% vs mensual
            </p>
          )}
        </div>

        {/* Meta bullets */}
        <div className="mb-4 pb-4 border-b border-slate-100">
          <div className="space-y-2 text-sm">
            <div className="flex items-center text-slate-700">
              <span className="mr-2 text-brand-500 font-bold">🏪</span>
              <span>{meta.branches}</span>
            </div>
            <div className="flex items-center text-slate-700">
              <span className="mr-2 text-brand-500 font-bold">👥</span>
              <span>{meta.users}</span>
            </div>
            <div className="flex items-center text-slate-700 font-semibold">
              <span className="mr-2 text-brand-500">✨</span>
              <span>{meta.highlight}</span>
            </div>
          </div>
        </div>

        {/* Checklist de features */}
        <ul className="space-y-2 flex-1">
          {GC_PLAN_KEY_FEATURES[plan.plan].map((feature) => (
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

export function GestionComercialPlanBuilder({
  billingPeriod,
  onSubscribe,
}: GestionComercialPlanBuilderProps) {
  const handleSubscribe = (plan: GcPlanEntry) => {
    onSubscribe({
      plan: plan.plan,
      planCode: planCodeFor(plan.plan),
    });
  };

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-stretch">
        {GC_PLANS.map((plan) => (
          <PlanCard
            key={plan.plan}
            plan={plan}
            billingPeriod={billingPeriod}
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
