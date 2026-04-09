import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'Funciones — Mirubro',
    description:
        'Operaciones multi-tenant, workflows composables y observabilidad activa. Diseñado para equipos modernos que buscan escalar sin duplicar infraestructura.',
    alternates: { canonical: 'https://www.mirubro.com/features' },
    openGraph: {
        title: 'Funciones — Mirubro',
        description:
            'Operaciones multi-tenant, workflows composables y observabilidad activa. Diseñado para equipos modernos.',
        url: 'https://www.mirubro.com/features',
        siteName: 'Mirubro',
        type: 'website',
        locale: 'es_AR',
    },
    twitter: {
        card: 'summary_large_image',
        title: 'Funciones — Mirubro',
        description:
            'Operaciones multi-tenant, workflows composables y observabilidad activa. Diseñado para equipos modernos.',
    },
};

const features = [
    {
        title: 'Operaciones multi-tenant',
        description: 'Aísla datos por negocio sin duplicar infraestructura.',
    },
    {
        title: 'Workflows composables',
        description: 'Orquesta ventas, stock y caja con APIs consistentes.',
    },
    {
        title: 'Observabilidad activa',
        description: 'Detecta riesgos y métricas clave en dashboards en tiempo real.',
    },
];

export default function FeaturesPage() {
    return (
        <section className="space-y-8">
            <header className="space-y-3">
                <p className="text-sm font-semibold text-brand-500">Funciones claves</p>
                <h1 className="text-3xl font-display font-bold text-slate-900">Diseñado para equipos modernos</h1>
                <p className="text-slate-600">
                    Crea experiencias diferenciadas para marketing y el producto sin perder consistencia.
                </p>
            </header>
            <div className="grid gap-6 md:grid-cols-3">
                {features.map((feature) => (
                    <article key={feature.title} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                        <h2 className="text-xl font-semibold text-slate-900">{feature.title}</h2>
                        <p className="mt-2 text-sm text-slate-600">{feature.description}</p>
                    </article>
                ))}
            </div>
        </section>
    );
}
