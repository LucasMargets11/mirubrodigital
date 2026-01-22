const tiers = [
    { name: 'Starter', price: '$49', highlights: ['Hasta 3 tiendas', 'Soporte estándar'] },
    { name: 'Growth', price: '$149', highlights: ['Hasta 10 tiendas', 'Soporte prioritario'] },
    { name: 'Enterprise', price: 'Custom', highlights: ['Multi-tenant ilimitado', 'CSM dedicado'] },
];

export default function PricingPage() {
    return (
        <section className="space-y-10">
            <header className="space-y-3">
                <p className="text-sm font-semibold text-brand-500">Precios transparentes</p>
                <h1 className="text-3xl font-display font-bold text-slate-900">Elige tu próximo nivel</h1>
                <p className="text-slate-600">Escala de marketing a operaciones sin migraciones dolorosas.</p>
            </header>
            <div className="grid gap-6 md:grid-cols-3">
                {tiers.map((tier) => (
                    <article key={tier.name} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                        <h2 className="text-xl font-semibold text-slate-900">{tier.name}</h2>
                        <p className="text-3xl font-bold text-slate-900">{tier.price}</p>
                        <ul className="mt-4 space-y-2 text-sm text-slate-600">
                            {tier.highlights.map((highlight) => (
                                <li key={highlight}>• {highlight}</li>
                            ))}
                        </ul>
                    </article>
                ))}
            </div>
        </section>
    );
}
