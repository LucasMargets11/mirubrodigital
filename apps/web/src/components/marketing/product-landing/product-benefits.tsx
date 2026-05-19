import { SiteContainer } from '@/components/layout/site-container';
import type { LucideIcon } from 'lucide-react';

export type BenefitItem = {
    title: string;
    description: string;
    icon: LucideIcon;
};

export type ProductBenefitsProps = {
    label?: string;
    title: string;
    subtitle?: string;
    benefits: BenefitItem[];
};

export function ProductBenefits({ label, title, subtitle, benefits }: ProductBenefitsProps) {
    return (
        <section className="py-16 lg:py-24 bg-slate-50/60">
            <SiteContainer>
                <div className="max-w-2xl space-y-3">
                    {label && (
                        <p className="text-sm font-semibold uppercase tracking-[0.25em] text-brand-600">
                            {label}
                        </p>
                    )}
                    <h2 className="text-3xl font-display font-bold text-slate-900">{title}</h2>
                    {subtitle && (
                        <p className="text-base leading-relaxed text-slate-600">{subtitle}</p>
                    )}
                </div>

                <div className="mt-10 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
                    {benefits.map((b) => {
                        const Icon = b.icon;
                        return (
                            <article
                                key={b.title}
                                className="flex h-full flex-col rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm transition hover:shadow-md"
                            >
                                <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl border border-brand-100 bg-brand-50 text-brand-600">
                                    <Icon className="h-5 w-5" aria-hidden />
                                </div>
                                <h3 className="text-base font-semibold leading-snug text-slate-950">
                                    {b.title}
                                </h3>
                                <p className="mt-3 text-sm leading-6 text-slate-600">
                                    {b.description}
                                </p>
                            </article>
                        );
                    })}
                </div>
            </SiteContainer>
        </section>
    );
}
