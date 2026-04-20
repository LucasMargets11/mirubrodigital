import Link from 'next/link';
import type { Route } from 'next';
import { Button } from '@/components/ui/button';
import { ArrowRight, CheckCircle2 } from 'lucide-react';
import { SiteContainer } from '@/components/layout/site-container';

export type ProductHeroProps = {
    label: string;
    title: string;
    titleAccent?: string;
    subtitle: string;
    ctaHref: string;
    ctaLabel: string;
    secondaryHref?: string;
    secondaryLabel?: string;
    proofPoints?: string[];
    /** Render a visual mockup to the right of the text. */
    mockup?: React.ReactNode;
};

export function ProductHero({
    label,
    title,
    titleAccent,
    subtitle,
    ctaHref,
    ctaLabel,
    secondaryHref,
    secondaryLabel,
    proofPoints,
    mockup,
}: ProductHeroProps) {
    return (
        <section className="relative w-full overflow-hidden bg-white py-20 lg:py-28">
            {/* Background Decor */}
            <div className="absolute inset-0 -z-10 pointer-events-none overflow-hidden">
                <div className="absolute top-[-10%] right-[-5%] w-[40%] h-[40%] bg-brand-50/60 rounded-full blur-3xl opacity-50" />
                <div className="absolute bottom-[-10%] left-[-10%] w-[30%] h-[30%] bg-indigo-50/60 rounded-full blur-3xl opacity-50" />
            </div>

            <SiteContainer>
                <div className="grid gap-12 lg:grid-cols-2 lg:gap-16 items-start lg:min-h-[420px]">
                    {/* Text — always starts from the same vertical position */}
                    <div className="max-w-xl space-y-6 lg:pt-4">
                        <p className="text-sm font-semibold uppercase tracking-[0.25em] text-brand-600">
                            {label}
                        </p>

                        <h1
                            className="font-display font-bold text-slate-900 tracking-tight leading-[1.1]"
                            style={{ fontSize: 'clamp(2rem, 4vw, 3.5rem)' }}
                        >
                            {title}
                            {titleAccent && (
                                <>
                                    {' '}
                                    <span className="text-brand-600">{titleAccent}</span>
                                </>
                            )}
                        </h1>

                        <p className="text-lg text-slate-600 leading-relaxed max-w-lg">
                            {subtitle}
                        </p>

                        {/* CTAs */}
                        <div className="flex flex-col sm:flex-row gap-4 pt-2">
                            <Button
                                asChild
                                size="lg"
                                className="h-12 px-8 text-base text-white shadow-lg shadow-brand-500/25 hover:shadow-xl hover:shadow-brand-500/40 transition-shadow font-semibold bg-brand-600 hover:bg-brand-500"
                            >
                                <Link href={ctaHref as Route}>
                                    {ctaLabel}
                                    <ArrowRight className="ml-2 h-4 w-4" />
                                </Link>
                            </Button>
                            {secondaryHref && secondaryLabel && (
                                <Button
                                    asChild
                                    variant="outline"
                                    size="lg"
                                    className="h-12 px-8 text-base border-slate-200 hover:bg-slate-50 text-slate-700 bg-transparent"
                                >
                                    <Link href={secondaryHref as Route}>{secondaryLabel}</Link>
                                </Button>
                            )}
                        </div>

                        {/* Proof */}
                        {proofPoints && proofPoints.length > 0 && (
                            <div className="pt-4 border-t border-slate-100">
                                <div className="flex flex-wrap gap-x-6 gap-y-3 text-sm font-medium text-slate-500">
                                    {proofPoints.map((point) => (
                                        <span key={point} className="flex items-center gap-2">
                                            <CheckCircle2 className="h-4 w-4 text-brand-500 flex-shrink-0" />
                                            {point}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Mockup — self-centered; never affects text position */}
                    <div className="relative w-full flex items-center justify-center lg:justify-end lg:self-center select-none max-h-[480px]">
                        {mockup}
                    </div>
                </div>
            </SiteContainer>
        </section>
    );
}
