import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { SiteContainer } from '@/components/layout/site-container';

export function ContactCTA() {
    return (
        <section className="bg-slate-50 py-20 lg:py-28">
            <SiteContainer className="text-center">
                <h2 className="mx-auto max-w-xl font-display text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
                    ¿Querés conocer más sobre Mi&nbsp;Rubro?
                </h2>

                <p className="mx-auto mt-4 max-w-lg text-base leading-relaxed text-slate-600 sm:text-lg">
                    Podés escribirnos, solicitar una demo o explorar nuestras
                    soluciones para encontrar la mejor opción para tu negocio.
                </p>

                <div className="mt-8 flex flex-col items-center justify-center gap-4 sm:flex-row">
                    <Link
                        href={'/contacto' as never}
                        className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-500"
                    >
                        Solicitar demo
                        <ArrowRight className="h-4 w-4" />
                    </Link>
                    <Link
                        href={'/planes' as never}
                        className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-6 py-3 text-sm font-semibold text-slate-700 transition hover:border-brand-300 hover:text-brand-600"
                    >
                        Ver planes
                    </Link>
                </div>
            </SiteContainer>
        </section>
    );
}
