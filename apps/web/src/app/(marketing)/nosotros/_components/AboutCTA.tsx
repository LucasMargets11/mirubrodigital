import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { SiteContainer } from '@/components/layout/site-container';

export function AboutCTA() {
    return (
        <section className="py-20 lg:py-28">
            <SiteContainer className="text-center">
                <h2 className="mx-auto max-w-xl font-display text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
                    ¿Querés saber más sobre nuestros productos?
                </h2>

                <p className="mx-auto mt-4 max-w-lg text-base leading-relaxed text-slate-600 sm:text-lg">
                    Explorá los planes disponibles o contactanos para recibir una
                    demo personalizada.
                </p>

                <div className="mt-8 flex flex-col items-center justify-center gap-4 sm:flex-row">
                    <Link
                        href={'/planes' as never}
                        className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-500"
                    >
                        Ver planes
                        <ArrowRight className="h-4 w-4" />
                    </Link>

                    <Link
                        href={'/contacto' as never}
                        className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-6 py-3 text-sm font-semibold text-slate-700 transition hover:border-brand-300 hover:text-brand-600"
                    >
                        Solicitar demo
                    </Link>
                </div>
            </SiteContainer>
        </section>
    );
}
