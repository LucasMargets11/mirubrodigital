import Link from 'next/link';

export default function PlansPage() {
    return (
        <section className="mx-auto max-w-2xl space-y-6 rounded-2xl border border-dashed border-slate-300 bg-white/80 p-8 text-center">
            <p className="text-sm font-semibold uppercase tracking-wide text-brand-500">Tu plan no está activo</p>
            <h1 className="text-3xl font-display font-bold text-slate-900">Activa Mirubro para continuar</h1>
            <p className="text-slate-600">
                Necesitas una suscripción activa para acceder al panel. Gestioná tu plan o vuelve a marketing para
                conocer las opciones disponibles.
            </p>
            <div className="flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
                <Link
                    href="/pricing"
                    className="rounded-full bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-brand-500/40 shadow-lg"
                >
                    Ver planes
                </Link>
                <Link href="/" className="rounded-full border border-slate-300 px-6 py-3 text-sm font-semibold text-slate-700">
                    Ir al sitio marketing
                </Link>
            </div>
        </section>
    );
}
