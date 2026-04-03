import Link from 'next/link';
import type { Route } from 'next';
import { Button } from '@/components/ui/button';
import { SiteContainer } from '@/components/layout/site-container';
import { Check, ArrowRight } from 'lucide-react';

export type PricingCardData = {
    name: string;
    tagline: string;
    price: string;
    period?: string;
    highlights: string[];
    ctaHref: string;
    ctaLabel: string;
    featured?: boolean;
};

export type ProductPricingProps = {
    label?: string;
    title: string;
    subtitle?: string;
    plans: PricingCardData[];
};

export function ProductPricing({ label, title, subtitle, plans }: ProductPricingProps) {
    return (
        <section className="py-16 lg:py-24">
            <SiteContainer>
                <div className="space-y-10">
                    <div className="text-center max-w-2xl mx-auto space-y-3">
                        {label && (
                            <p className="text-sm font-semibold uppercase tracking-[0.25em] text-brand-600">
                                {label}
                            </p>
                        )}
                        <h2 className="text-3xl font-display font-bold text-slate-900">{title}</h2>
                        {subtitle && <p className="text-lg text-slate-600">{subtitle}</p>}
                    </div>

                    <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 max-w-4xl mx-auto">
                        {plans.map((plan) => (
                            <div
                                key={plan.name}
                                className={`rounded-2xl border p-6 flex flex-col ${
                                    plan.featured
                                        ? 'border-brand-200 bg-brand-50/30 shadow-lg ring-1 ring-brand-100'
                                        : 'border-slate-200 bg-white shadow-sm'
                                }`}
                            >
                                <div className="space-y-1">
                                    <h3 className="text-lg font-semibold text-slate-900">{plan.name}</h3>
                                    <p className="text-sm text-slate-500">{plan.tagline}</p>
                                </div>

                                <div className="mt-4">
                                    <span className="text-3xl font-bold text-slate-900">{plan.price}</span>
                                    {plan.period && (
                                        <span className="text-sm text-slate-500 ml-1">{plan.period}</span>
                                    )}
                                </div>

                                <ul className="mt-6 space-y-2.5 flex-1">
                                    {plan.highlights.map((h) => (
                                        <li key={h} className="flex items-start gap-2 text-sm text-slate-600">
                                            <Check className="h-4 w-4 mt-0.5 text-brand-500 flex-shrink-0" />
                                            {h}
                                        </li>
                                    ))}
                                </ul>

                                <div className="mt-6">
                                    <Button
                                        asChild
                                        size="lg"
                                        className={`w-full ${
                                            plan.featured
                                                ? 'bg-brand-600 hover:bg-brand-500 text-white'
                                                : ''
                                        }`}
                                        variant={plan.featured ? 'default' : 'outline'}
                                    >
                                        <Link href={plan.ctaHref as Route}>
                                            {plan.ctaLabel}
                                            <ArrowRight className="ml-2 h-4 w-4" />
                                        </Link>
                                    </Button>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </SiteContainer>
        </section>
    );
}
