import Link from 'next/link';
import { Headphones, ArrowRight } from 'lucide-react';

export function ContactSupportRedirect() {
    return (
        <section className="rounded-2xl border border-slate-200 bg-slate-50 p-6">
            <div className="flex items-start gap-4">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                    <Headphones className="h-5 w-5" />
                </span>
                <div>
                    <h2 className="font-display text-lg font-semibold text-slate-900">
                        ¿Necesitás ayuda técnica?
                    </h2>
                    <p className="mt-2 text-sm leading-relaxed text-slate-600">
                        Si ya usás Mi&nbsp;Rubro y necesitás ayuda con tu
                        cuenta, configuración, uso de la plataforma o un
                        inconveniente técnico, te recomendamos ingresar a la
                        sección de soporte.
                    </p>
                    <Link
                        href={'/soporte' as never}
                        className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-brand-600 transition hover:text-brand-500"
                    >
                        Ir a soporte
                        <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                </div>
            </div>
        </section>
    );
}
