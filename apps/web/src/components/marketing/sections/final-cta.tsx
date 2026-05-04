import Link from 'next/link';
import { Button } from '@/components/ui/button';

export function FinalCtaSection() {
    return (
        <section className="py-16">
            <div className="mx-auto max-w-7xl px-6 lg:px-10">
                <div className="rounded-3xl border border-primary/20 bg-primary/5 px-8 py-10 shadow-sm">
                    <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
                        <div className="space-y-2">
                            <p className="text-sm font-semibold uppercase tracking-[0.25em] text-primary">
                                Empezá hoy
                            </p>
                            <h2 className="text-3xl font-semibold text-zinc-900">
                                ¿Listo para centralizar tu operación?
                            </h2>
                            <p className="text-base text-zinc-600">
                                Conecta equipos, canales y decisiones en una sola plataforma.
                            </p>
                        </div>
                        <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-center">
                            <Button
                                asChild
                                className="h-12 rounded-xl bg-brand-600 px-6 text-base font-medium text-white shadow-sm transition-colors hover:bg-brand-700 md:h-14 md:px-7"
                            >
                                <Link href="/entrar">Comenzar gratis</Link>
                            </Button>
                            <Button
                                asChild
                                variant="outline"
                                className="h-12 rounded-xl border-slate-300 bg-white px-6 text-base font-medium text-slate-900 transition-colors hover:bg-slate-50 md:h-14 md:px-7"
                            >
                                <Link href="/pricing">Ver precios</Link>
                            </Button>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
