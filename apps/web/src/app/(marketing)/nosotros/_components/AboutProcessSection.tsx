import { SiteContainer } from '@/components/layout/site-container';
import { PROCESS_PILLARS } from '../_data';

export function AboutProcessSection() {
    return (
        <section className="bg-slate-50 py-20 lg:py-28">
            <SiteContainer>
                <div className="mx-auto max-w-2xl text-center">
                    <p className="text-sm font-semibold uppercase tracking-wider text-brand-600">
                        Nuestra forma de trabajo
                    </p>
                    <h2 className="mt-2 font-display text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
                        ¿Cómo trabajamos?
                    </h2>
                </div>

                <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
                    {PROCESS_PILLARS.map((pillar, i) => (
                        <div key={pillar.title} className="text-center">
                            <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-brand-600 font-display text-sm font-bold text-white">
                                {i + 1}
                            </div>
                            <h3 className="mt-4 font-display text-lg font-semibold text-slate-900">
                                {pillar.title}
                            </h3>
                            <p className="mt-2 text-sm leading-relaxed text-slate-600">
                                {pillar.text}
                            </p>
                        </div>
                    ))}
                </div>
            </SiteContainer>
        </section>
    );
}
