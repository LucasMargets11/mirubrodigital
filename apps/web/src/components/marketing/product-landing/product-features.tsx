import { SiteContainer } from '@/components/layout/site-container';
import { Card } from '@/components/ui/card';
import type { LucideIcon } from 'lucide-react';

export type FeatureItem = {
    title: string;
    description: string;
    icon: LucideIcon;
};

export type ProductFeaturesProps = {
    label?: string;
    title: string;
    subtitle?: string;
    features: FeatureItem[];
};

export function ProductFeatures({ label, title, subtitle, features }: ProductFeaturesProps) {
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

                    <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                        {features.map((f) => {
                            const Icon = f.icon;
                            return (
                                <Card key={f.title} className="space-y-4 border-slate-200 p-6">
                                    <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-50 text-brand-600 shadow-inner">
                                        <Icon className="h-5 w-5" aria-hidden />
                                    </div>
                                    <div>
                                        <h3 className="text-lg font-semibold text-slate-900">{f.title}</h3>
                                        <p className="mt-1.5 text-sm text-slate-600 leading-relaxed">
                                            {f.description}
                                        </p>
                                    </div>
                                </Card>
                            );
                        })}
                    </div>
                </div>
            </SiteContainer>
        </section>
    );
}
