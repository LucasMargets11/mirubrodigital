import { Store, QrCode, Star } from 'lucide-react';
import { SiteContainer } from '@/components/layout/site-container';
import { PRODUCT_CARDS } from '../_data';

const ICONS = [Store, QrCode, Star] as const;

export function AboutProductsSection() {
    return (
        <section className="py-20 lg:py-28">
            <SiteContainer>
                <div className="mx-auto max-w-2xl text-center">
                    <p className="text-sm font-semibold uppercase tracking-wider text-brand-600">
                        Productos
                    </p>
                    <h2 className="mt-2 font-display text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
                        ¿Qué ofrecemos?
                    </h2>
                </div>

                <div className="mt-12 grid gap-8 sm:grid-cols-3">
                    {PRODUCT_CARDS.map((card, i) => {
                        const Icon = ICONS[i]!;
                        return (
                            <div
                                key={card.title}
                                className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
                            >
                                <div className="inline-flex rounded-xl bg-brand-50 p-2.5 text-brand-600">
                                    <Icon className="h-5 w-5" />
                                </div>
                                <h3 className="mt-4 font-display text-lg font-semibold text-slate-900">
                                    {card.title}
                                </h3>
                                <p className="mt-2 text-sm leading-relaxed text-slate-600">
                                    {card.text}
                                </p>
                            </div>
                        );
                    })}
                </div>
            </SiteContainer>
        </section>
    );
}
