import { Card } from '@/components/ui/card';
import { FEATURES } from './data';

export function FeaturesSection() {
    return (
        <section className="py-16">
            <div className="space-y-6">
                <p className="text-sm font-semibold uppercase tracking-[0.25em] text-primary">Producto</p>
                <h2 className="text-3xl font-semibold text-zinc-900">Funciones principales</h2>
                <p className="text-base text-zinc-600">
                    Diseñadas para operaciones exigentes, multi-sucursal y equipos que necesitan visibilidad real.
                </p>
                <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                    {FEATURES.map((feature) => {
                        const Icon = feature.icon;
                        return (
                            <Card key={feature.title} className="space-y-4 border-zinc-200 p-6">
                                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
                                    <Icon className="h-5 w-5" aria-hidden />
                                </div>
                                <div>
                                    <h3 className="text-xl font-semibold text-zinc-900">{feature.title}</h3>
                                    <p className="mt-2 text-sm text-zinc-600">{feature.description}</p>
                                </div>
                            </Card>
                        );
                    })}
                </div>
            </div>
        </section>
    );
}
