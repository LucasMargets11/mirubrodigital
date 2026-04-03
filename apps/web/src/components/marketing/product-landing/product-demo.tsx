import { SiteContainer } from '@/components/layout/site-container';

export type ProductDemoProps = {
    label?: string;
    title: string;
    subtitle?: string;
    /** The visual element: screenshot, mockup, or embedded UI */
    children: React.ReactNode;
};

export function ProductDemo({ label, title, subtitle, children }: ProductDemoProps) {
    return (
        <section className="py-16 lg:py-24">
            <SiteContainer>
                <div className="space-y-10">
                    <div className="text-center max-w-2xl mx-auto space-y-3">
                        {label && (
                            <p className="text-sm font-semibold uppercase tracking-[0.25em] text-brand-600">
                                {label}
                            </p>
                        )}
                        <h2 className="text-3xl font-display font-bold text-slate-900">{title}</h2>
                        {subtitle && <p className="text-lg text-slate-600">{subtitle}</p>}
                    </div>

                    <div className="relative mx-auto max-w-5xl">
                        {/* Browser chrome mockup */}
                        <div className="rounded-xl border border-slate-200 bg-white shadow-xl overflow-hidden">
                            <div className="h-8 bg-slate-50 border-b border-slate-100 flex items-center gap-1.5 px-4">
                                <div className="flex gap-1.5">
                                    <div className="w-2.5 h-2.5 rounded-full bg-red-400/20 border border-red-500/30" />
                                    <div className="w-2.5 h-2.5 rounded-full bg-amber-400/20 border border-amber-500/30" />
                                    <div className="w-2.5 h-2.5 rounded-full bg-emerald-400/20 border border-emerald-500/30" />
                                </div>
                                <div className="ml-4 flex-1 h-4 bg-white rounded-md border border-slate-100 max-w-[240px]" />
                            </div>
                            <div className="relative aspect-[16/9] bg-slate-50">
                                {children}
                            </div>
                        </div>
                    </div>
                </div>
            </SiteContainer>
        </section>
    );
}
