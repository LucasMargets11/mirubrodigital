import { CheckCircle2 } from 'lucide-react';
import { SiteContainer } from '@/components/layout/site-container';
import { WHY_CHOOSE } from '../_data';

export function AboutWhyChoose() {
    return (
        <section className="py-20 lg:py-28">
            <SiteContainer>
                <div className="mx-auto max-w-2xl text-center">
                    <p className="text-sm font-semibold uppercase tracking-wider text-brand-600">
                        Diferencial
                    </p>
                    <h2 className="mt-2 font-display text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
                        ¿Por qué elegir Mi&nbsp;Rubro?
                    </h2>
                </div>

                <ul className="mx-auto mt-10 grid max-w-3xl gap-4 sm:grid-cols-2">
                    {WHY_CHOOSE.map((item) => (
                        <li key={item} className="flex items-start gap-3">
                            <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-brand-600" />
                            <span className="text-base leading-relaxed text-slate-700">
                                {item}
                            </span>
                        </li>
                    ))}
                </ul>
            </SiteContainer>
        </section>
    );
}
