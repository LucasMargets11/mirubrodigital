import { HOW_IT_WORKS_STEPS } from './data';

export function HowItWorksSection() {
    return (
        <section className="py-16">
            <div className="mx-auto max-w-7xl px-6 lg:px-10">
                <div className="space-y-6">
                <p className="text-sm font-semibold uppercase tracking-[0.25em] text-primary">Implementación</p>
                <h2 className="text-3xl font-semibold text-zinc-900">¿Cómo funciona?</h2>
                <div className="grid gap-6 md:grid-cols-3">
                    {HOW_IT_WORKS_STEPS.map((step, index) => (
                        <div
                            key={step.title}
                            className="rounded-3xl border border-zinc-200 bg-white p-6 shadow-sm"
                        >
                            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-base font-semibold text-primary">
                                {index + 1}
                            </div>
                            <h3 className="mt-4 text-xl font-semibold text-zinc-900">{step.title}</h3>
                            <p className="mt-2 text-sm text-zinc-600">{step.description}</p>
                        </div>
                    ))}
                </div>
            </div>
            </div>
        </section>
    );
}
