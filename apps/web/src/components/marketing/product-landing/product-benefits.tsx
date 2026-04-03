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
                <div className="space-y-10">
                    <div className="max-w-2xl space-y-3">
                        {label && (
                            <p className="text-sm font-semibold uppercase tracking-[0.25em] text-brand-600">
                                {label}
                            </p>
                        )}
                        <h2 className="text-3xl font-display font-bold text-slate-900">{title}</h2>
                        {subtitle && <p className="text-lg text-slate-600">{subtitle}</p>}
                    </div>

                    <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-3">
                        {benefits.map((b) => {
                            const Icon = b.icon;
                            return (
                                <div key={b.title} className="space-y-3">
                                    <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-50 text-brand-600 shadow-inner">
                                        <Icon className="h-5 w-5" aria-hidden />
                                    </div>
                                    <h3 className="text-lg font-semibold text-slate-900">{b.title}</h3>
                                    <p className="text-sm text-slate-600 leading-relaxed">{b.description}</p>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </SiteContainer>
        </section>
    );
}
