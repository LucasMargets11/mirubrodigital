import { useState } from 'react';
import Link from 'next/link';
import {
  getAddon,
  getPlanPrice,
  getPlansForVertical,
  getProduct,
  getUsageTier,
} from '@/lib/pricing/selectors';
import { formatPrice } from '@/lib/pricing/format';
import type { BillingCycle, CanonicalPlanDef } from '@/lib/pricing/types';
import { apiPost } from '@/lib/api/client';

type AppointmentsPricingSectionProps = {
  billingPeriod: BillingCycle;
};

const CONTACT_HREF = '/contacto';
const PRODUCT_HREF = '/turnos';

type AppointmentQuoteRequest = {
  plan_code: string;
  billing_cycle: BillingCycle;
  usage_tier?: string;
  automations?: boolean;
  extra_professionals: number;
};

type AppointmentQuote = {
  plan_code: string;
  billing_cycle: BillingCycle;
  base_amount: number;
  addons_amount: number;
  extras_amount: number;
  total_amount: number;
  line_items: Array<{
    code: string;
    description: string;
    quantity: number;
    unit_price: number;
    total: number;
    included?: boolean;
  }>;
};

function getQuoteErrorMessage(error: unknown): string {
  if (typeof error !== 'object' || error === null) {
    return 'No pudimos obtener la cotización. Intentá nuevamente más tarde.';
  }
  const status = 'status' in error && typeof error.status === 'number' ? error.status : undefined;
  const payload =
    'payload' in error && typeof error.payload === 'object' && error.payload !== null
      ? error.payload
      : undefined;
  const code =
    payload && 'code' in payload && typeof payload.code === 'string' ? payload.code : undefined;

  if (status === 401) {
    return 'Iniciá sesión con una cuenta propietaria para solicitar una cotización.';
  }
  if (status === 403 && code === 'owner_required') {
    return 'Solo el propietario del negocio puede solicitar esta cotización.';
  }
  if (status === 403 && code === 'business_context_ambiguous') {
    return 'Seleccioná el negocio que querés cotizar y volvé a intentarlo.';
  }
  if (status === 403) {
    return 'Iniciá sesión con una cuenta que tenga acceso activo al negocio.';
  }
  if (status === 400) {
    return 'Revisá el plan y las opciones seleccionadas para solicitar la cotización.';
  }
  return 'No pudimos obtener la cotización. Intentá nuevamente más tarde.';
}

export function AppointmentsPricingSection({ billingPeriod }: AppointmentsPricingSectionProps) {
  const product = getProduct('appointments');
  const plans = getPlansForVertical('appointments');
  const aiPlan = plans.find((plan) => plan.code === 'appointments_ai');
  const automationAddon = getAddon('appointments_automations');

  if (!product || !aiPlan?.usageTiers?.length || !automationAddon) {
    throw new Error('El catálogo de precios debe incluir los planes de Turnos y sus tiers.');
  }

  const tiers = aiPlan.usageTiers.map((code) => {
    const tier = getUsageTier(code);
    if (!tier || tier.planCode !== aiPlan.code) {
      throw new Error(`Tier de Turnos IA inválido: ${code}`);
    }
    return tier;
  });

  return (
    <section
      aria-label="Planes informativos de Turnos"
      className="space-y-6"
      data-testid="appointments-pricing"
    >
      {!product.is_active && (
        <p className="text-center text-sm font-medium text-slate-500">
          Contratación online próximamente
        </p>
      )}

      <div className="grid items-stretch gap-6 lg:grid-cols-3">
        {plans.map((plan) => (
          <article
            key={plan.code}
            className="flex h-full flex-col rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
            data-plan-code={plan.code}
            data-testid="appointments-plan"
          >
            <h2 className="font-display text-2xl font-bold text-slate-900">{plan.name}</h2>
            <PlanHighlights
              plan={plan}
              plans={plans}
              billingPeriod={billingPeriod}
              automationAddon={automationAddon}
            />

            {plan.code === aiPlan.code ? (
              <div className="mt-6 border-t border-slate-100 pt-5">
                <p className="mb-4 text-sm text-slate-600">
                  Cada precio corresponde al plan IA completo; no se suma el precio de Turnos Pro.
                </p>
                <div className="grid gap-3 xl:grid-cols-2">
                  {tiers.map((tier) => (
                    <div
                      key={tier.code}
                      className="flex flex-col rounded-xl border border-slate-200 bg-slate-50 p-4"
                      data-tier-code={tier.code}
                      data-testid={`appointments-ai-tier-${tier.code}`}
                    >
                      <h3 className="font-semibold text-slate-900">
                        {tier.purchaseMode === 'contact_sales' ? 'A medida' : tier.name}
                      </h3>
                      {tier.purchaseMode === 'contact_sales' ? (
                        <>
                          <p className="mt-2 text-sm text-slate-600">
                            Sesiones y precio a coordinar con nuestro equipo comercial.
                          </p>
                          <Link
                            className="mt-4 font-semibold text-brand-600 hover:text-brand-700"
                            href={CONTACT_HREF}
                          >
                            Contactar ventas
                          </Link>
                        </>
                      ) : (
                        <>
                          <p className="mt-2 text-sm text-slate-600">
                            {tier.includedConversations.toLocaleString('es-AR')} sesiones / mes
                          </p>
                          <p className="mt-3 font-semibold text-slate-900">
                            {formatPrice(getPlanPrice(aiPlan, billingPeriod, tier.code))}
                            <span className="ml-1 text-sm font-normal text-slate-500">
                              / {billingPeriod === 'monthly' ? 'mes' : 'año'}
                            </span>
                          </p>
                          <p className="mt-2 text-sm text-slate-600">
                            Sesión adicional: {formatPrice(tier.extraConversationPrice)}
                          </p>
                          <p className="mt-1 text-sm text-slate-600">
                            Límite predeterminado de consumo adicional:{' '}
                            {formatPrice(tier.defaultExtraSpendLimit)}
                          </p>
                          <AiTierQuote
                            planCode={aiPlan.code}
                            tierCode={tier.code}
                            billingPeriod={billingPeriod}
                          />
                          <Link
                            className="mt-4 font-semibold text-brand-600 hover:text-brand-700"
                            href={PRODUCT_HREF}
                          >
                            Más información
                          </Link>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <>
                <p className="mt-4 text-3xl font-bold text-slate-900">
                  {formatPrice(getPlanPrice(plan, billingPeriod))}
                  <span className="ml-2 text-sm font-normal text-slate-500">
                    / {billingPeriod === 'monthly' ? 'mes' : 'año'}
                  </span>
                </p>
                <FixedPlanQuote
                  plan={plan}
                  billingPeriod={billingPeriod}
                  automationAddon={automationAddon}
                />
                <Link
                  className="mt-6 font-semibold text-brand-600 hover:text-brand-700"
                  href={PRODUCT_HREF}
                >
                  Más información
                </Link>
              </>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

type FixedPlanQuoteProps = {
  plan: CanonicalPlanDef;
  billingPeriod: BillingCycle;
  automationAddon: NonNullable<ReturnType<typeof getAddon>>;
};

function FixedPlanQuote({ plan, billingPeriod, automationAddon }: FixedPlanQuoteProps) {
  const [automations, setAutomations] = useState(false);
  const [extraProfessionals, setExtraProfessionals] = useState(0);

  return (
    <div className="mt-5 space-y-4 border-t border-slate-100 pt-4">
      {automationAddon.availableFor.includes(plan.code) && (
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            aria-label={`${plan.name}: incluir automatizaciones`}
            checked={automations}
            onChange={(event) => setAutomations(event.target.checked)}
          />
          Incluir {automationAddon.name}
        </label>
      )}
      <label className="flex items-center justify-between gap-3 text-sm text-slate-700">
        Profesionales extra
        <input
          aria-label={`${plan.name}: profesionales extra`}
          className="w-24 rounded-md border border-slate-300 px-2 py-1"
          type="number"
          min={0}
          step={1}
          value={extraProfessionals}
          onChange={(event) => setExtraProfessionals(Number(event.target.value))}
        />
      </label>
      <QuoteAction
        key={`${plan.code}-${billingPeriod}-${automations}-${extraProfessionals}`}
        request={{
          plan_code: plan.code,
          billing_cycle: billingPeriod,
          automations,
          extra_professionals: extraProfessionals,
        }}
      />
    </div>
  );
}

type AiTierQuoteProps = {
  planCode: string;
  tierCode: string;
  billingPeriod: BillingCycle;
};

function AiTierQuote({ planCode, tierCode, billingPeriod }: AiTierQuoteProps) {
  const [extraProfessionals, setExtraProfessionals] = useState(0);

  return (
    <div className="mt-4 space-y-3">
      <p className="text-sm font-medium text-slate-700">Automatizaciones incluidas</p>
      <label className="flex items-center justify-between gap-3 text-sm text-slate-700">
        Profesionales extra
        <input
          aria-label={`${tierCode}: profesionales extra`}
          className="w-24 rounded-md border border-slate-300 px-2 py-1"
          type="number"
          min={0}
          step={1}
          value={extraProfessionals}
          onChange={(event) => setExtraProfessionals(Number(event.target.value))}
        />
      </label>
      <QuoteAction
        key={`${tierCode}-${billingPeriod}-${extraProfessionals}`}
        request={{
          plan_code: planCode,
          billing_cycle: billingPeriod,
          usage_tier: tierCode,
          automations: true,
          extra_professionals: extraProfessionals,
        }}
      />
    </div>
  );
}

function QuoteAction({ request }: { request: AppointmentQuoteRequest }) {
  const [loading, setLoading] = useState(false);
  const [quote, setQuote] = useState<AppointmentQuote | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function requestQuote() {
    setLoading(true);
    setError(null);
    setQuote(null);
    try {
      const result = await apiPost<AppointmentQuote>(
        '/api/v1/billing/appointments/quote/',
        request,
      );
      setQuote(result);
    } catch (requestError) {
      setError(getQuoteErrorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-3" data-testid="appointments-quote-action">
      <button
        className="rounded-lg border border-brand-600 px-4 py-2 text-sm font-semibold text-brand-700 hover:bg-brand-50 disabled:cursor-wait disabled:opacity-60"
        type="button"
        disabled={loading}
        onClick={requestQuote}
      >
        {loading ? 'Calculando cotización…' : 'Consultar cotización actualizada'}
      </button>
      {error && (
        <p className="text-sm text-red-700" role="alert">
          {error}
        </p>
      )}
      {quote && <QuoteSummary quote={quote} />}
    </div>
  );
}

function QuoteSummary({ quote }: { quote: AppointmentQuote }) {
  const planNames: Record<string, string> = {
    appointments: 'Turnos Base',
    appointments_pro: 'Turnos Pro',
    appointments_ai: 'Turnos IA Recepcionista',
  };

  return (
    <section
      aria-label="Cotización calculada por el servidor"
      className="rounded-xl bg-slate-50 p-4 text-sm text-slate-700"
      data-testid="appointments-quote-result"
    >
      <h3 className="font-semibold text-slate-900">Cotización actualizada</h3>
      <dl className="mt-3 grid grid-cols-2 gap-2">
        <dt>Plan</dt>
        <dd>{planNames[quote.plan_code] ?? quote.plan_code}</dd>
        <dt>Ciclo</dt>
        <dd>{quote.billing_cycle === 'monthly' ? 'Mensual' : 'Anual'}</dd>
        <dt>Base</dt>
        <dd>{formatPrice(quote.base_amount)}</dd>
        <dt>Adicionales</dt>
        <dd>{formatPrice(quote.addons_amount)}</dd>
        <dt>Profesionales extra</dt>
        <dd>{formatPrice(quote.extras_amount)}</dd>
      </dl>
      <ul className="mt-3 space-y-1 border-t border-slate-200 pt-3">
        {quote.line_items.map((item) => (
          <li key={item.code}>
            {item.description}: {item.quantity} × {formatPrice(item.unit_price)} ={' '}
            {formatPrice(item.total)}
            {item.included ? ' (incluido)' : ''}
          </li>
        ))}
      </ul>
      <p className="mt-3 border-t border-slate-200 pt-3 font-bold text-slate-900">
        Total: {formatPrice(quote.total_amount)}
      </p>
    </section>
  );
}

type PlanHighlightsProps = {
  plan: CanonicalPlanDef;
  plans: CanonicalPlanDef[];
  billingPeriod: BillingCycle;
  automationAddon: NonNullable<ReturnType<typeof getAddon>>;
};

function PlanHighlights({ plan, plans, billingPeriod, automationAddon }: PlanHighlightsProps) {
  if (plan.professionalsIncluded == null || plan.secondaryUsersIncluded == null) {
    throw new Error(`El plan ${plan.code} debe declarar sus recursos incluidos.`);
  }

  const includedPlanNames = (plan.includesPlans ?? []).map((code) => {
    const includedPlan = plans.find((candidate) => candidate.code === code);
    if (!includedPlan) {
      throw new Error(`El plan ${plan.code} incluye un plan inválido: ${code}`);
    }
    return includedPlan.name;
  });

  const automationLabel = automationAddon.includedIn.includes(plan.code)
    ? `${automationAddon.name} incluidas`
    : automationAddon.availableFor.includes(plan.code)
      ? `${automationAddon.name} como adicional opcional (${formatPrice(
          billingPeriod === 'monthly' ? automationAddon.priceMonthly : automationAddon.priceYearly,
        )} / ${billingPeriod === 'monthly' ? 'mes' : 'año'})`
      : null;

  return (
    <ul className="mt-4 space-y-2 border-t border-slate-100 pt-4 text-sm text-slate-700">
      <li>Agenda, horarios y reservas vinculadas a clientes</li>
      <li>{plan.professionalsIncluded.toLocaleString('es-AR')} profesionales incluidos</li>
      <li>{plan.secondaryUsersIncluded.toLocaleString('es-AR')} usuarios secundarios incluidos</li>
      {includedPlanNames.map((name) => (
        <li key={name}>Incluye {name}</li>
      ))}
      {automationLabel && <li>{automationLabel}</li>}
      {plan.pricingMode === 'usage_tier' && <li>Sesiones de IA según el tier elegido</li>}
    </ul>
  );
}
