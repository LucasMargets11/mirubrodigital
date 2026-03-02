'use client';

import { useState } from 'react';
import { Info } from 'lucide-react';
import {
  QR_PLANS,
  QR_ADDONS,
  PRO_MODULE_OPTIONS,
  formatArsPrice,
  type QrPlanEntry,
  type ProModule,
} from '../data/menu-qr-catalog';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface MenuQrSubscribeConfig {
  plan: 'lite' | 'pro' | 'premium';
  planCode: string;
  proIncludedModule?: ProModule;
  addonCodes: string[];
  totalMonthly: number;
  totalYearly: number;
}

interface MenuQrPlanBuilderProps {
  billingPeriod: 'monthly' | 'yearly';
  onSubscribe: (config: MenuQrSubscribeConfig) => void;
  /** Called whenever PRO module selection or add-on toggle changes */
  onProStateChange?: (module: ProModule | null, addonEnabled: boolean) => void;
}

// ---------------------------------------------------------------------------
// Pricing helpers
// ---------------------------------------------------------------------------

const ADDON_PRICE_MONTHLY = 990; // ARS
const ADDON_PRICE_YEARLY = 9504; // ARS (10% descuento aprox)

function planCodeFor(plan: QrPlanEntry['plan']): string {
  return `menu_qr_${plan}`;
}

function calculateTotal(
  plan: QrPlanEntry,
  period: 'monthly' | 'yearly',
  addonCount: number
): number {
  const base = period === 'monthly' ? plan.priceMonthly : plan.priceYearly;
  const addonPrice = period === 'monthly' ? ADDON_PRICE_MONTHLY : ADDON_PRICE_YEARLY;
  return base + addonCount * addonPrice;
}

// ---------------------------------------------------------------------------
// Features bullets per plan
// ---------------------------------------------------------------------------

const PLAN_KEY_FEATURES: Record<QrPlanEntry['plan'], string[]> = {
  lite: [
    'Editor de carta digital',
    'Branding (logo y colores)',
    'URL + QR único imprimible',
    'Analítica básica',
  ],
  pro: [
    'Todo lo incluido en Lite',
    'Fotos por producto',
    'Analítica avanzada',
    '1 módulo de engagement incluido',
    'Add-on del segundo módulo disponible',
  ],
  premium: [
    'Todo lo incluido en Pro',
    'Reseñas de Google',
    'Propinas (MP link, QR y dinámico)',
    'Dominio personalizado',
    'Multi-sucursal',
  ],
};

const PLAN_META: Record<QrPlanEntry['plan'], { highlight: string }> = {
  lite: { highlight: 'Ideal para empezar' },
  pro: { highlight: 'Elegís 1 módulo de engagement' },
  premium: { highlight: 'Engagement completo incluido' },
};

// ---------------------------------------------------------------------------
// ProModuleSelector — injected inside the PRO card between checklist and CTA
// ---------------------------------------------------------------------------

function ProModuleSelector({
  includedModule,
  addonEnabled,
  onChange,
}: {
  includedModule: ProModule | null;
  addonEnabled: boolean;
  onChange: (module: ProModule | null, addon: boolean) => void;
}) {
  const handleModuleChange = (mod: ProModule) => {
    const addonOption = PRO_MODULE_OPTIONS.find((o) => o.value !== mod);
    const keepAddon = addonEnabled && addonOption !== undefined;
    onChange(mod, keepAddon);
  };

  const handleAddonToggle = () => {
    onChange(includedModule, !addonEnabled);
  };

  const otherModuleOption = includedModule
    ? PRO_MODULE_OPTIONS.find((o) => o.value !== includedModule)
    : null;

  return (
    <div className="mt-4 rounded-xl border border-brand-200 bg-brand-50 p-3.5 space-y-3">
      <div>
        <p className="text-xs font-semibold text-brand-700 uppercase tracking-wider mb-2">
          Elegí tu módulo incluido
        </p>
        <div className="space-y-1.5">
          {PRO_MODULE_OPTIONS.map((opt) => {
            const isSelected = includedModule === opt.value;
            return (
              <label
                key={opt.value}
                className={`flex items-start gap-2.5 rounded-lg border px-3 py-2.5 cursor-pointer transition-all ${
                  isSelected
                    ? 'border-brand-500 bg-white shadow-sm'
                    : 'border-slate-200 bg-white hover:border-brand-300'
                }`}
              >
                <input
                  type="radio"
                  name="pro-included-module"
                  value={opt.value}
                  checked={isSelected}
                  onChange={() => handleModuleChange(opt.value)}
                  className="mt-0.5 accent-brand-600 flex-shrink-0"
                />
                <div>
                  <p className="text-sm font-semibold text-slate-800">{opt.label}</p>
                  <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{opt.description}</p>
                </div>
              </label>
            );
          })}
        </div>
        {!includedModule && (
          <p className="mt-2 text-xs text-amber-700 flex items-center gap-1">
            <Info className="w-3 h-3 flex-shrink-0" aria-hidden="true" />
            Seleccioná un módulo para continuar con el plan PRO.
          </p>
        )}
      </div>
      {includedModule && otherModuleOption && (
        <div className="border-t border-brand-200 pt-3 flex items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="text-xs font-medium text-slate-800 leading-tight">
              + Add-on{' '}
              <span className="font-semibold text-brand-700">{otherModuleOption.label}</span>
            </p>
            <p className="text-[11px] text-slate-500">
              +{formatArsPrice(ADDON_PRICE_MONTHLY)}/mes
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={addonEnabled}
            aria-label={`Activar add-on ${otherModuleOption.label}`}
            onClick={handleAddonToggle}
            className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 transition-colors duration-200 ease-in-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 ${
              addonEnabled ? 'bg-brand-600 border-brand-600' : 'bg-slate-200 border-slate-200'
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                addonEnabled ? 'translate-x-4' : 'translate-x-0'
              }`}
            />
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Individual plan card — same structure/classes as PlansBundles (GC reference)
// ---------------------------------------------------------------------------

function PlanCard({
  plan,
  billingPeriod,
  proIncludedModule,
  proAddonEnabled,
  onProChange,
  onSubscribe,
}: {
  plan: QrPlanEntry;
  billingPeriod: 'monthly' | 'yearly';
  proIncludedModule: ProModule | null;
  proAddonEnabled: boolean;
  onProChange: (module: ProModule | null, addon: boolean) => void;
  onSubscribe: (p: QrPlanEntry) => void;
}) {
  const isRecommended = plan.isRecommended ?? false;
  const addonCount = plan.plan === 'pro' && proAddonEnabled ? 1 : 0;
  const totalPrice = calculateTotal(plan, billingPeriod, addonCount);
  const monthlyEquiv =
    billingPeriod === 'yearly' ? Math.round(totalPrice / 12) : totalPrice;
  const canSubscribe = plan.plan !== 'pro' || proIncludedModule !== null;

  return (
    <div
      className={`h-full border rounded-2xl bg-white shadow-sm hover:shadow-lg transition-all ${
        isRecommended
          ? 'border-brand-500 ring-2 ring-brand-500 scale-[1.02]'
          : 'border-slate-200'
      }`}
    >
      <div className="h-full flex flex-col p-6">
        {/* Badge — espacio reservado igual que GC */}
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
              {formatArsPrice(monthlyEquiv)}
            </span>
            <span className="text-slate-500 text-sm ml-2">/ mes</span>
          </div>
          {billingPeriod === 'yearly' && (
            <p className="text-green-600 text-xs font-semibold mt-1">
              Ahorrás 20% vs mensual
            </p>
          )}
          {plan.plan === 'pro' && proAddonEnabled && (
            <p className="text-brand-600 text-xs font-semibold mt-1">
              Plan + add-on incluidos
            </p>
          )}
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
          {PLAN_KEY_FEATURES[plan.plan].map((m) => (
            <li key={m} className="flex items-start text-sm text-slate-700">
              <span className="mr-2 text-green-500 font-bold">✓</span>
              <span>{m}</span>
            </li>
          ))}
        </ul>

        {/* PRO: selector de módulo incluido */}
        {plan.plan === 'pro' && (
          <ProModuleSelector
            includedModule={proIncludedModule}
            addonEnabled={proAddonEnabled}
            onChange={onProChange}
          />
        )}

        {/* CTA — alineado al fondo igual que GC */}
        <div className="mt-auto pt-6">
          <button
            type="button"
            onClick={() => canSubscribe && onSubscribe(plan)}
            disabled={!canSubscribe}
            aria-disabled={!canSubscribe}
            className={`w-full py-3 px-4 rounded-lg font-semibold transition-all ${
              !canSubscribe
                ? 'bg-slate-100 text-slate-400 cursor-not-allowed'
                : isRecommended
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

export function MenuQrPlanBuilder({ billingPeriod, onSubscribe, onProStateChange }: MenuQrPlanBuilderProps) {
  const [proIncludedModule, setProIncludedModule] = useState<ProModule | null>(null);
  const [proAddonEnabled, setProAddonEnabled] = useState(false);

  const handleProChange = (module: ProModule | null, addon: boolean) => {
    setProIncludedModule(module);
    setProAddonEnabled(addon);
    onProStateChange?.(module, addon);
  };

  const handleSubscribe = (plan: QrPlanEntry) => {
    const addonCount = plan.plan === 'pro' && proAddonEnabled ? 1 : 0;

    const addonCodes: string[] = [];
    if (plan.plan === 'pro' && proAddonEnabled && proIncludedModule) {
      const otherAddon = QR_ADDONS.find(
        (a) =>
          a.featureKey !==
          (proIncludedModule === 'reviews' ? 'menu_qr_reviews' : 'menu_qr_tips')
      );
      if (otherAddon) addonCodes.push(otherAddon.code);
    }

    onSubscribe({
      plan: plan.plan,
      planCode: planCodeFor(plan.plan),
      proIncludedModule: plan.plan === 'pro' ? proIncludedModule ?? undefined : undefined,
      addonCodes,
      totalMonthly: calculateTotal(plan, 'monthly', addonCount),
      totalYearly: calculateTotal(plan, 'yearly', addonCount),
    });
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-stretch">
      {QR_PLANS.map((plan) => (
        <PlanCard
          key={plan.plan}
          plan={plan}
          billingPeriod={billingPeriod}
          proIncludedModule={proIncludedModule}
          proAddonEnabled={proAddonEnabled}
          onProChange={handleProChange}
          onSubscribe={handleSubscribe}
        />
      ))}
    </div>
  );
}
