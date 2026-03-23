import {
    LayoutGrid,
    Smartphone,
    Users,
    Settings2,
} from 'lucide-react';
import { SiteContainer } from '@/components/layout/site-container';
import { PROBLEM_CARDS } from '../_data';

const ICONS = [LayoutGrid, Smartphone, Users, Settings2] as const;

export function AboutProblemSection() {
    return (
        <section className="bg-slate-50 py-20 lg:py-28">
            <SiteContainer>
                <div className="mx-auto max-w-2xl text-center">
                    <p className="text-sm font-semibold uppercase tracking-wider text-brand-600">
                        Nuestra motivación
                    </p>
                    <h2 className="mt-2 font-display text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
                        ¿Qué nos impulsa?
                    </h2>
                    <p className="mt-4 text-base leading-relaxed text-slate-600 sm:text-lg">
                        Muchos comercios todavía dependen de procesos manuales,
                        información dispersa o herramientas que no se adaptan a
                        su realidad. Mi&nbsp;Rubro nace con la intención de
                        aportar soluciones concretas a esos desafíos.
                    </p>
                </div>

                <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
                    {PROBLEM_CARDS.map((card, i) => {
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
