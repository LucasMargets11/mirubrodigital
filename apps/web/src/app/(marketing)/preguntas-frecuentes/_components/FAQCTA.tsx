import Link from 'next/link';
import { ArrowRight } from 'lucide-react';

export function FAQCTA() {
    return (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-6 py-10 text-center sm:px-10">
            <h2 className="font-display text-xl font-semibold text-slate-900 sm:text-2xl">
                ¿No encontraste lo que buscabas?
            </h2>
            <p className="mt-3 text-base text-slate-600">
                Escribinos y te ayudamos a resolver tu consulta.
            </p>

            <div className="mt-6 flex flex-col items-center justify-center gap-3 sm:flex-row">
                <Link
                    href={'/soporte' as never}
                    className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-brand-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
                >
                    Contactar soporte
                    <ArrowRight className="h-4 w-4" />
                </Link>
                <Link
                    href={'/contacto' as never}
                    className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-6 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition-all hover:border-brand-300 hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
                >
                    Solicitar demo
                </Link>
            </div>
        </div>
    );
}
