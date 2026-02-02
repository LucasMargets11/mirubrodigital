import Link from 'next/link';

export default function MarketingHomePage() {
    return (
        <section className="flex flex-1 flex-col justify-center space-y-8">
            <div className="space-y-4">
                <p className="text-sm font-semibold uppercase tracking-wide text-brand-500">
                    SaaS multi-tenant
                </p>
                <h1 className="text-4xl font-display font-bold text-slate-900">
                    Centraliza tus operaciones en minutos
                </h1>
                <p className="text-lg text-slate-600">
                    Lanza rápidamente áreas de marketing y aplicación operativa con una base pensada para
                    equipos modernos.
                </p>
            </div>
            <div className="flex flex-wrap gap-4">
                <Link
                    href="/app"
                    className="rounded-full bg-brand-600 px-6 py-3 text-white shadow-lg shadow-brand-200"
                >
                    Ir al panel
                </Link>
                <Link href="/pricing" className="rounded-full border border-slate-200 px-6 py-3 text-slate-700">
                    Ver precios
                </Link>
            </div>
        </section>
    );
}
