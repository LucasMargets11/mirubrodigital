import { TRUST_LOGOS } from './data';

export function TrustSection() {
    return (
        <section className="py-12">
            <div className="mx-auto max-w-7xl px-6 lg:px-10">
                <div className="flex flex-col gap-6">
                <p className="text-center text-sm font-semibold uppercase tracking-[0.3em] text-zinc-400">
                    Usado por equipos que venden y operan todos los días
                </p>
                <div className="flex flex-wrap items-center justify-center gap-6 text-sm font-medium text-zinc-500">
                    {TRUST_LOGOS.map((logo) => (
                        <span
                            key={logo}
                            className="rounded-full border border-dashed border-zinc-200 px-4 py-2 text-zinc-600"
                        >
                            {logo}
                        </span>
                    ))}
                </div>
            </div>
            </div>
        </section>
    );
}
