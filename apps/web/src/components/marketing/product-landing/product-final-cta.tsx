import Link from 'next/link';
import type { Route } from 'next';
import { Button } from '@/components/ui/button';
import { SiteContainer } from '@/components/layout/site-container';
import { ArrowRight } from 'lucide-react';

export type ProductFinalCtaProps = {
    title: string;
    subtitle: string;
    ctaHref: string;
    ctaLabel: string;
    secondaryHref?: string;
    secondaryLabel?: string;
};

export function ProductFinalCta({
    title,
    subtitle,
    ctaHref,
    ctaLabel,
    secondaryHref,
    secondaryLabel,
}: ProductFinalCtaProps) {
    return (
        <section className="py-16 lg:py-20">
            <SiteContainer>
                <div className="rounded-3xl border border-brand-200/40 bg-gradient-to-br from-brand-50/60 to-white px-8 py-12 shadow-sm">
                    <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
                        <div className="space-y-2 max-w-lg">
                            <h2 className="text-3xl font-display font-bold text-slate-900">{title}</h2>
                            <p className="text-base text-slate-600">{subtitle}</p>
                        </div>
                        <div className="flex flex-wrap gap-3">
                            <Button
                                asChild
                                size="lg"
                                className="h-12 px-8 text-base shadow-lg shadow-brand-500/25 font-semibold bg-brand-600 hover:bg-brand-500"
                            >
                                <Link href={ctaHref as Route}>
                                    {ctaLabel}
                                    <ArrowRight className="ml-2 h-4 w-4" />
                                </Link>
                            </Button>
                            {secondaryHref && secondaryLabel && (
                                <Button asChild size="lg" variant="outline" className="h-12 px-8 text-base">
                                    <Link href={secondaryHref as Route}>{secondaryLabel}</Link>
                                </Button>
                            )}
                        </div>
                    </div>
                </div>
            </SiteContainer>
        </section>
    );
}
