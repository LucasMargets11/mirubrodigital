import Link from 'next/link';
import { Button } from '@/components/ui/button';

export function FinalCtaSection() {
    return (
        <section className="py-16">
            <div className="mx-auto max-w-7xl px-6 lg:px-10">
                <div className="rounded-3xl border border-primary/20 bg-primary/5 px-8 py-10 shadow-sm">
                <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
                    <div className="space-y-2">
                        <p className="text-sm font-semibold uppercase tracking-[0.25em] text-primary">CTA</p>
                        <h2 className="text-3xl font-semibold text-zinc-900">¿Listo para centralizar tu operación?</h2>
                        <p className="text-base text-zinc-600">
                            Conecta equipos, canales y decisiones en una sola plataforma.
                        </p>
                    </div>
                    <div className="flex flex-wrap gap-3">
                        <Button asChild size="lg">
                            <Link href="/app">Ir al panel</Link>
                        </Button>
                        <Button asChild size="lg" variant="outline">
                            <Link href="/pricing">Ver precios</Link>
                        </Button>
                    </div>
                </div>
            </div>
            </div>
        </section>
    );
}
