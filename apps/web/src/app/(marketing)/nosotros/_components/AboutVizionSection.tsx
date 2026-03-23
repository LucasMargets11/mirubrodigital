import { Lightbulb, Layers, Code2 } from 'lucide-react';
import { SiteContainer } from '@/components/layout/site-container';
import { VIZION_PILLARS } from '../_data';

const ICONS = [Lightbulb, Layers, Code2] as const;

export function AboutVizionSection() {
    return (
        <section className="relative overflow-hidden bg-slate-900 py-20 lg:py-28">
            {/* Decorative gradient */}
            <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-brand-600/20 via-transparent to-transparent"
            />

            <SiteContainer className="relative">
                <div className="mx-auto max-w-2xl text-center">
                    <p className="text-sm font-semibold uppercase tracking-wider text-brand-400">
                        Detrás de Mi Rubro
                    </p>
                    <h2 className="mt-2 font-display text-2xl font-bold tracking-tight text-white sm:text-3xl">
                        Desarrollado por Estudio&nbsp;VIZION
                    </h2>
                    <p className="mt-4 text-base leading-relaxed text-slate-300 sm:text-lg">
                        Estudio VIZION es el equipo detrás del diseño, desarrollo
                        y evolución de Mi&nbsp;Rubro. Trabajamos con foco en
                        crear productos digitales que resuelvan necesidades reales
                        de forma clara y escalable.
                    </p>
                </div>

                <div className="mt-12 grid gap-8 sm:grid-cols-3">
                    {VIZION_PILLARS.map((pillar, i) => {
                        const Icon = ICONS[i]!;
                        return (
                            <div
                                key={pillar.title}
                                className="rounded-2xl border border-slate-700/60 bg-slate-800/60 p-6 backdrop-blur-sm"
                            >
                                <div className="inline-flex rounded-xl bg-brand-600/20 p-2.5 text-brand-400">
                                    <Icon className="h-5 w-5" />
                                </div>
                                <h3 className="mt-4 font-display text-lg font-semibold text-white">
                                    {pillar.title}
                                </h3>
                                <p className="mt-2 text-sm leading-relaxed text-slate-400">
                                    {pillar.text}
                                </p>
                            </div>
                        );
                    })}
                </div>
            </SiteContainer>
        </section>
    );
}
