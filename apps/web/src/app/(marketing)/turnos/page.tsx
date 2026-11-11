import type { Metadata } from 'next';
import Link from 'next/link';
import { Bot, CalendarDays, ClipboardList, Clock, Link2, Users, Zap } from 'lucide-react';
import { SiteContainer } from '@/components/layout/site-container';
import { ProductBenefits } from '@/components/marketing/product-landing/product-benefits';
import { ProductFeatures } from '@/components/marketing/product-landing/product-features';
import { ProductFinalCta } from '@/components/marketing/product-landing/product-final-cta';
import { ProductHero } from '@/components/marketing/product-landing/product-hero';
import {
  ProductPricing,
  type PricingCardData,
} from '@/components/marketing/product-landing/product-pricing';
import { ProductSteps } from '@/components/marketing/product-landing/product-steps';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ADDON_APPOINTMENTS_AUTOMATIONS } from '@/lib/pricing/addons';
import { formatPrice } from '@/lib/pricing/format';
import {
  getPlanPrice,
  getPlansForVertical,
  getProduct,
  getUsageTier,
} from '@/lib/pricing/selectors';
import type { CanonicalPlanDef } from '@/lib/pricing/types';
import { ReceptionistDemoSection } from './receptionist-demo-section';

const SITE_URL = 'https://www.mirubro.com';
const CONTACT_HREF = '/contacto';
const DESCRIPTION =
  'Gestioná agenda, profesionales, clientes y reservas desde Mi Rubro. Conocé los planes de Turnos y las opciones de IA Recepcionista.';

export const metadata: Metadata = {
  title: 'MiRubro Turnos — Agenda y reservas | Mi Rubro',
  description: DESCRIPTION,
  alternates: { canonical: `${SITE_URL}/turnos` },
  openGraph: {
    title: 'MiRubro Turnos — Agenda y reservas | Mi Rubro',
    description: DESCRIPTION,
    url: `${SITE_URL}/turnos`,
    siteName: 'Mirubro',
    type: 'website',
    locale: 'es_AR',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'MiRubro Turnos — Agenda y reservas | Mi Rubro',
    description: DESCRIPTION,
  },
};

function pricingCard(plan: CanonicalPlanDef): PricingCardData {
  const automations = ADDON_APPOINTMENTS_AUTOMATIONS;
  const tiered = plan.pricingMode === 'usage_tier';
  return {
    name: plan.name,
    tagline: tiered
      ? 'Todo lo de Turnos Pro, con IA Recepcionista.'
      : 'Agenda, profesionales, clientes y reservas en un solo lugar.',
    price: tiered ? 'Según sesiones' : formatPrice(getPlanPrice(plan, 'monthly')),
    period: tiered ? undefined : 'ARS / mes',
    highlights: [
      `${plan.professionalsIncluded} profesionales incluidos`,
      `${plan.secondaryUsersIncluded} usuarios secundarios incluidos`,
      ...(automations.includedIn.includes(plan.code)
        ? [`${automations.name} incluidas`]
        : automations.availableFor.includes(plan.code)
          ? [`${automations.name} como adicional opcional`]
          : []),
      ...(tiered
        ? ['Un solo plan IA, con tiers según sesiones', 'Consultá los tiers debajo']
        : [`Pago anual: ${formatPrice(getPlanPrice(plan, 'yearly'))} ARS en total`]),
    ],
    // Esta landing es informativa: publicar el producto no habilita checkout.
    ctaHref: CONTACT_HREF,
    ctaLabel: 'Consultar plan',
  };
}

export default function TurnosPage() {
  const product = getProduct('appointments');
  const plans = getPlansForVertical('appointments');
  const aiPlan = plans.find((plan) => plan.code === 'appointments_ai');
  if (!product || !aiPlan?.usageTiers?.length) {
    throw new Error('El catálogo de Turnos debe incluir el producto y los tiers de IA.');
  }
  const tiers = aiPlan.usageTiers.map((code) => {
    const tier = getUsageTier(code);
    if (!tier || tier.planCode !== aiPlan.code) {
      throw new Error(`Tier de Turnos IA inválido: ${code}`);
    }
    return tier;
  });

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            '@context': 'https://schema.org',
            '@type': 'SoftwareApplication',
            name: 'MiRubro Turnos',
            description: DESCRIPTION,
            url: `${SITE_URL}/turnos`,
            applicationCategory: 'BusinessApplication',
            operatingSystem: 'Web',
            // Sin offers: los precios son informativos, no una oferta contratable online.
            publisher: {
              '@type': 'Organization',
              name: 'Mirubro',
              url: SITE_URL,
            },
          }),
        }}
      />

      <ProductHero
        label="MiRubro Turnos"
        titlePrimary="Tu agenda, más ordenada."
        titleSecondary="Tus reservas, en un solo lugar."
        subtitle="Gestioná la agenda de tu negocio, los profesionales, los clientes y las reservas desde Mi Rubro. Definí horarios y compartí tu enlace de reserva."
        ctaHref="#planes-turnos"
        ctaLabel="Conocer planes"
        secondaryHref={CONTACT_HREF}
        secondaryLabel="Hablar con nosotros"
        proofPoints={['Agenda centralizada', 'Profesionales', 'Reservas online']}
        mockup={
          <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-slate-50 p-6 shadow-sm">
            <Badge variant="outline" className="border-brand-200 text-brand-600">
              Vista ilustrativa
            </Badge>
            <p className="mt-4 font-display text-2xl font-bold text-slate-900">
              Tu negocio, conectado
            </p>
            <p className="mt-2 text-sm text-slate-600">
              Un espacio para organizar cada parte de tu atención.
            </p>
            <div className="mt-6 grid grid-cols-2 gap-3">
              {[
                { label: 'Agenda', icon: CalendarDays },
                { label: 'Profesionales', icon: Users },
                { label: 'Clientes', icon: ClipboardList },
                { label: 'Reservas', icon: Link2 },
              ].map(({ label, icon: Icon }) => (
                <div
                  key={label}
                  className="min-w-0 rounded-2xl border border-slate-200 bg-white p-3"
                >
                  <Icon className="h-5 w-5 text-brand-600" aria-hidden />
                  <p className="mt-3 break-words text-sm font-medium text-slate-900">{label}</p>
                </div>
              ))}
            </div>
          </div>
        }
      />

      <ProductBenefits
        label="Más organización"
        title="Menos dispersión en el día a día"
        benefits={[
          {
            title: 'Agenda centralizada',
            description: 'Consultá y administrá los turnos de tu negocio desde Mi Rubro.',
            icon: CalendarDays,
          },
          {
            title: 'Cada profesional, organizado',
            description: 'Gestioná profesionales y sus horarios de atención en el mismo espacio.',
            icon: Users,
          },
          {
            title: 'Reservas y clientes conectados',
            description: 'Vinculá las reservas con tus clientes y consultá su historial de turnos.',
            icon: ClipboardList,
          },
        ]}
      />

      <ProductSteps
        label="Cómo funciona"
        title="De la configuración a la reserva"
        steps={[
          {
            title: 'Configurá tu negocio',
            description:
              'Cargá tus servicios y profesionales, y definí sus horarios y disponibilidad.',
          },
          {
            title: 'Compartí tu enlace',
            description: 'Tus clientes acceden al enlace público de tu negocio para reservar.',
          },
          {
            title: 'Administrá tu agenda',
            description: 'Consultá las reservas y gestioná la atención desde Mi Rubro.',
          },
        ]}
      />

      <ReceptionistDemoSection />

      <ProductFeatures
        label="Capacidades"
        title="Una base común, opciones según tu plan"
        subtitle="Todos los planes incluyen la gestión de agenda, profesionales, clientes y reservas. Los recursos incluidos y las opciones de automatización varían según el plan."
        features={[
          {
            title: 'Disponibilidad de atención',
            description: 'Definí horarios y excepciones para organizar cuándo se puede reservar.',
            icon: Clock,
          },
          {
            title: 'Automatizaciones según plan',
            description: `${ADDON_APPOINTMENTS_AUTOMATIONS.name} como adicional en ${plans
              .filter((plan) => ADDON_APPOINTMENTS_AUTOMATIONS.availableFor.includes(plan.code))
              .map((plan) => plan.name)
              .join(' y ')}, e incluidas en ${plans
              .filter((plan) => ADDON_APPOINTMENTS_AUTOMATIONS.includedIn.includes(plan.code))
              .map((plan) => plan.name)
              .join(' y ')}.`,
            icon: Zap,
          },
          {
            title: 'IA Recepcionista',
            description:
              'Un plan que incluye Turnos Pro y automatizaciones, con tiers de sesiones según las necesidades de tu negocio.',
            icon: Bot,
          },
        ]}
      />

      <div id="planes-turnos" className="scroll-mt-24">
        <SiteContainer className="pt-16 text-center">
          {!product.is_active && (
            <Badge variant="outline" className="border-slate-200 text-slate-600">
              Próximamente disponible para contratación online
            </Badge>
          )}
        </SiteContainer>
        <ProductPricing
          label="Planes de Turnos"
          title="Elegí cómo organizar tu atención"
          subtitle="Precios informativos en ARS. Mostramos el precio mensual y el total del pago anual, sin alternar ciclos ni iniciar una compra."
          plans={plans.map(pricingCard)}
        />
      </div>

      <section className="bg-slate-50 py-16 lg:py-24" aria-labelledby="turnos-ia-title">
        <SiteContainer>
          <div className="max-w-2xl space-y-3">
            <p className="text-sm font-semibold uppercase tracking-[0.25em] text-brand-600">
              IA Recepcionista
            </p>
            <h2 id="turnos-ia-title" className="font-display text-3xl font-bold text-slate-900">
              Un plan IA, distintos tiers de sesiones
            </h2>
            <p className="text-base leading-relaxed text-slate-600">
              Cada precio corresponde al plan IA completo: incluye Turnos Pro y automatizaciones. No
              se suma el precio de Pro. Las sesiones incluidas son mensuales.
            </p>
          </div>
          <dl className="mt-10 grid gap-5 md:grid-cols-2 xl:grid-cols-4">
            {tiers.map((tier) => (
              <div
                key={tier.code}
                className="min-w-0 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
              >
                <dt className="font-display text-xl font-bold text-slate-900">{tier.name}</dt>
                <dd className="mt-4 space-y-3 text-sm text-slate-600">
                  {tier.purchaseMode === 'contact_sales' ? (
                    <>
                      <p className="font-semibold text-slate-900">A medida</p>
                      <p>Sesiones y precio a coordinar con nuestro equipo comercial.</p>
                      <Button
                        asChild
                        variant="link"
                        className="h-auto whitespace-normal p-0 text-brand-600"
                      >
                        <Link href={CONTACT_HREF}>Consultar opción a medida</Link>
                      </Button>
                    </>
                  ) : (
                    <>
                      <p>{tier.includedConversations.toLocaleString('es-AR')} sesiones / mes</p>
                      <p className="font-semibold text-slate-900">
                        {formatPrice(getPlanPrice(aiPlan, 'monthly', tier.code))} ARS / mes
                      </p>
                      <p>
                        Pago anual: {formatPrice(getPlanPrice(aiPlan, 'yearly', tier.code))} ARS en
                        total
                      </p>
                    </>
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </SiteContainer>
      </section>

      <ProductFinalCta
        title="Hablemos de tu agenda"
        subtitle="Te ayudamos a conocer los planes de Turnos y la opción adecuada para tu negocio."
        ctaHref={CONTACT_HREF}
        ctaLabel="Contactar"
        secondaryHref="#planes-turnos"
        secondaryLabel="Conocer planes"
      />
    </>
  );
}
