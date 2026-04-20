import Link from 'next/link';
import type { Route } from 'next';
import { Button } from '@/components/ui/button';
import { SiteContainer } from '@/components/layout/site-container';
import { cn } from '@/lib/utils';
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
    badge?: string;
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

                    <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 max-w-4xl mx-auto items-stretch">
                        {plans.map((plan) => (
                            <div
                                key={plan.name}
                                className={cn(
                                    'rounded-2xl border bg-white flex flex-col h-full transition-all',
                                    plan.featured
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
                                    <h3 className="text-2xl font-bold text-slate-900 mb-1">{plan.name}</h3>
                                    <p className="text-sm text-slate-500 mb-4 min-h-[40px]">{plan.tagline}</p>

                                    {/* Price */}
                                    <div className="mb-5">
                                        <span className="text-3xl font-bold text-slate-900">{plan.price}</span>
                                        {plan.period && (
                                            <span className="text-sm text-slate-500 ml-1.5">{plan.period}</span>
                                        )}
                                    </div>

                                    {/* Key features */}
                                    <ul className="space-y-2 flex-1 mb-6 border-t border-slate-100 pt-4">
                                        {plan.highlights.map((h) => (
                                            <li key={h} className="flex items-start gap-2 text-sm text-slate-700">
                                                <Check className="h-4 w-4 mt-0.5 text-green-500 flex-shrink-0" />
                                                {h}
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
                                                plan.featured
                                                    ? 'bg-brand-600 hover:bg-brand-500 text-white shadow-md'
                                                    : 'bg-slate-100 text-slate-900 hover:bg-slate-200'
                                            )}
                                            variant={plan.featured ? 'default' : 'secondary'}
                                        >
                                            <Link href={plan.ctaHref as Route}>
                                                {plan.ctaLabel}
                                                <ArrowRight className="ml-2 h-4 w-4" />
                                            </Link>
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </SiteContainer>
        </section>
    );
}
