import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { PLANS } from './data';

export function PricingTeaserSection() {
    return (
        <section className="py-16">
            <div className="mx-auto max-w-7xl px-6 lg:px-10">
                <div className="space-y-6">
                <p className="text-sm font-semibold uppercase tracking-[0.25em] text-primary">Planes</p>
                <h2 className="text-3xl font-semibold text-zinc-900">Pensado para cada etapa</h2>
                <p className="text-base text-zinc-600">Elige el paquete correcto y escala cuando lo necesites.</p>
                <div className="grid gap-6 md:grid-cols-3">
                    {PLANS.map((plan) => (
                        <Card key={plan.name} className="flex flex-col border-zinc-200">
                            <CardHeader>
                                <CardTitle>{plan.name}</CardTitle>
                                <CardDescription>{plan.tagline}</CardDescription>
                            </CardHeader>
                            <CardContent className="flex flex-1 flex-col justify-between gap-6">
                                <div className="space-y-3">
                                    <p className="text-sm font-semibold text-zinc-900">{plan.priceNote}</p>
                                    <ul className="space-y-2 text-sm text-zinc-600">
                                        {plan.bullets.map((bullet) => (
                                            <li key={bullet} className="flex items-start gap-2">
                                                <span className="mt-1 h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />
                                                {bullet}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                                <Button asChild>
                                    <Link href="/pricing" aria-label={`Ver precios del plan ${plan.name}`}>
                                        {plan.ctaLabel}
                                    </Link>
                                </Button>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            </div>
            </div>
        </section>
    );
}
