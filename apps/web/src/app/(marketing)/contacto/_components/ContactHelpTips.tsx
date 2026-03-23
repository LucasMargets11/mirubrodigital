import Link from 'next/link';
import { Lightbulb, ArrowRight } from 'lucide-react';

const TIPS = [
    'Si querés conocer una solución, indicá cuál te interesa',
    'Si tenés un comercio o local, contanos brevemente qué necesitás',
    'Si preferís respuesta por WhatsApp, dejá tu número de contacto',
    'Para consultas técnicas, usá la sección de soporte',
    'También podés revisar las preguntas frecuentes',
] as const;

export function ContactHelpTips() {
    return (
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-start gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-50 text-amber-600">
                    <Lightbulb className="h-4 w-4" />
                </span>
                <h2 className="font-display text-lg font-semibold text-slate-900">
                    Antes de contactarnos
                </h2>
            </div>

            <ul className="mt-4 space-y-2.5">
                {TIPS.map((tip) => (
                    <li key={tip} className="flex items-start gap-2 text-sm leading-relaxed text-slate-600">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-slate-400" />
                        {tip}
                    </li>
                ))}
            </ul>

            <Link
                href={'/preguntas-frecuentes' as never}
                className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-brand-600 transition hover:text-brand-500"
            >
                Ver preguntas frecuentes
                <ArrowRight className="h-3.5 w-3.5" />
            </Link>
        </section>
    );
}
