import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { PAIN_POINTS, SOLUTIONS } from './data';

function BulletList({ items }: { items: string[] }) {
    return (
        <ul className="space-y-4">
            {items.map((item) => (
                <li key={item} className="flex items-start gap-3">
                    <span className="mt-1 h-2 w-2 rounded-full bg-primary" aria-hidden />
                    <span className="text-sm text-zinc-600">{item}</span>
                </li>
            ))}
        </ul>
    );
}

export function ProblemSolutionSection() {
    return (
        <section className="py-16">
            <div className="mx-auto max-w-7xl px-6 lg:px-10">
                <div className="space-y-6">
                <p className="text-sm font-semibold uppercase tracking-[0.25em] text-primary">Operación</p>
                <h2 className="text-3xl font-semibold text-zinc-900">Todo en un solo lugar</h2>
                <div className="grid gap-6 md:grid-cols-2">
                    <Card className="border-zinc-200">
                        <CardHeader>
                            <CardTitle>Dolores que frenan tu negocio</CardTitle>
                            <CardDescription>Caja, stock y equipos desconectados terminan en pérdidas.</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <BulletList items={PAIN_POINTS} />
                        </CardContent>
                    </Card>
                    <Card className="border-zinc-200">
                        <CardHeader>
                            <CardTitle>Soluciones Mirubro</CardTitle>
                            <CardDescription>Automatiza procesos claves y gana visibilidad diaria.</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <BulletList items={SOLUTIONS} />
                        </CardContent>
                    </Card>
                </div>
            </div>
            </div>
        </section>
    );
}
