import { SiteContainer } from '@/components/layout/site-container';

export type StepItem = {
    title: string;
    description: string;
};

export type ProductStepsProps = {
    label?: string;
    title: string;
    steps: StepItem[];
};

export function ProductSteps({ label, title, steps }: ProductStepsProps) {
    return (
        <section className="py-16 lg:py-24">
            <SiteContainer>
                <div className="space-y-10">
                    <div className="max-w-2xl space-y-3">
                        {label && (
                            <p className="text-sm font-semibold uppercase tracking-[0.25em] text-brand-600">
                                {label}
                            </p>
                        )}
                        <h2 className="text-3xl font-display font-bold text-slate-900">{title}</h2>
                    </div>

                    <div className="grid gap-6 md:grid-cols-3">
                        {steps.map((step, i) => (
                            <div
                                key={step.title}
                                className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
                            >
                                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-50 text-base font-semibold text-brand-600">
                                    {i + 1}
                                </div>
                                <h3 className="mt-4 text-xl font-semibold text-slate-900">{step.title}</h3>
                                <p className="mt-2 text-sm text-slate-600">{step.description}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </SiteContainer>
        </section>
    );
}
