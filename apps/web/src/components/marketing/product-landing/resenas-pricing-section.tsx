'use client';

import { SiteContainer } from '@/components/layout/site-container';
import { ProductPricing } from './product-pricing';
import { REVIEW_PRICING_CARDS, SMART_FILTER } from '@/features/reviews/product';

export function ResenasPricingSection() {
    return (
        <>
            <ProductPricing
                label="Planes"
                title="Elegí el plan que necesitás"
                subtitle="Empezá a sumar reseñas hoy. Actualizá cuando quieras más control."
                plans={REVIEW_PRICING_CARDS}
            />

            {/* Smart filter callout */}
            <section className="pb-16 lg:pb-24 -mt-8">
                <SiteContainer>
                    <div className="max-w-2xl mx-auto rounded-xl border border-indigo-100 bg-indigo-50/30 p-5 text-center space-y-2">
                        <p className="text-sm font-bold text-slate-800">{SMART_FILTER.headline}</p>
                        <p className="text-xs text-slate-600">{SMART_FILTER.description}</p>
                    </div>
                </SiteContainer>
            </section>
        </>
    );
}
