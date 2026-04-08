import Link from 'next/link';
import type { Route } from 'next';
import { ArrowRight, Check, Store, QrCode, Star } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { SiteContainer } from '@/components/layout/site-container';

type Product = {
    id: string;
    name: string;
    description: string;
    bullets: string[];
    ctaLabel: string;
    href: string;
    icon: typeof Store;
    accent: string;
    accentBg: string;
    accentBorder: string;
    accentLight: string;
};

const PRODUCTS: Product[] = [
    {
        id: 'gestion-comercial',
        name: 'Gestión Comercial',
        description: 'Controlá ventas, stock, caja y clientes desde un solo lugar.',
        bullets: [
            'Ventas, presupuestos y caja integrados',
            'Stock en tiempo real con alertas automáticas',
            'Reportes claros para tomar mejores decisiones',
        ],
        ctaLabel: 'Conocer Gestión Comercial',
        href: '/gestion',
        icon: Store,
        accent: 'text-brand-600',
        accentBg: 'bg-brand-50',
        accentBorder: 'border-brand-200',
        accentLight: 'bg-brand-500',
    },
    {
        id: 'carta-online',
        name: 'Carta Online',
        description: 'Mostrá tu menú con QR y una experiencia moderna para tus clientes.',
        bullets: [
            'Menú digital accesible por código QR',
            'Actualizá productos y precios al instante',
            'Diseño profesional con tu marca y colores',
        ],
        ctaLabel: 'Conocer Carta Online',
        href: '/carta',
        icon: QrCode,
        accent: 'text-violet-600',
        accentBg: 'bg-violet-50',
        accentBorder: 'border-violet-200',
        accentLight: 'bg-violet-500',
    },
    {
        id: 'qr-resenas',
        name: 'QR de Reseñas',
        description: 'Recibí más reseñas positivas y gestioná mejor el feedback de tu negocio.',
        bullets: [
            'QR dedicado para capturar reseñas de clientes',
            'Redirigí opiniones positivas a Google y redes',
            'Panel para analizar y responder el feedback',
        ],
        ctaLabel: 'Conocer QR de Reseñas',
        href: '/resenas',
        icon: Star,
        accent: 'text-amber-600',
        accentBg: 'bg-amber-50',
        accentBorder: 'border-amber-200',
        accentLight: 'bg-amber-500',
    },
];

export function ProductsSection() {
    return (
        <section className="bg-white py-20 lg:py-28" id="productos">
            <SiteContainer>
                {/* Header */}
                <div className="mx-auto max-w-2xl text-center mb-14 lg:mb-20">
                    <p className="text-sm font-semibold uppercase tracking-[0.2em] text-brand-600 mb-4">
                        Nuestros productos
                    </p>
                    <h2 className="text-3xl font-bold text-slate-900 tracking-tight sm:text-4xl lg:text-[2.75rem] leading-tight">
                        Elegí la herramienta ideal para tu negocio
                    </h2>
                    <p className="mt-5 text-lg text-slate-500 leading-relaxed">
                        Tres soluciones diseñadas para resolver necesidades reales. Empezá con la que más te sirva y sumá las demás cuando las necesites.
                    </p>
                </div>

                {/* Products Grid */}
                <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-3">
                    {PRODUCTS.map((product) => (
                        <ProductCard key={product.id} product={product} />
                    ))}
                </div>
            </SiteContainer>
        </section>
    );
}

function ProductCard({ product }: { product: Product }) {
    const Icon = product.icon;

    return (
        <Link
            href={product.href as Route}
            className="group relative flex flex-col h-full rounded-2xl border border-slate-200 bg-white p-8 shadow-sm transition-all duration-300 hover:shadow-xl hover:border-slate-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
        >
            {/* Icon */}
            <div className={cn(
                "flex h-14 w-14 items-center justify-center rounded-2xl mb-6 transition-colors",
                product.accentBg,
                product.accent,
            )}>
                <Icon className="h-7 w-7" strokeWidth={1.5} />
            </div>

            {/* Title */}
            <h3 className="text-xl font-bold text-slate-900 mb-3 group-hover:text-slate-800">
                {product.name}
            </h3>

            {/* Description */}
            <p className="text-slate-500 leading-relaxed mb-6">
                {product.description}
            </p>

            {/* Bullets */}
            <ul className="space-y-3 mb-8 flex-1">
                {product.bullets.map((bullet, idx) => (
                    <li key={idx} className="flex items-start gap-3 text-sm text-slate-600">
                        <span className={cn(
                            "mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full",
                            product.accentBg,
                        )}>
                            <Check className={cn("h-3 w-3", product.accent)} strokeWidth={3} />
                        </span>
                        <span>{bullet}</span>
                    </li>
                ))}
            </ul>

            {/* CTA */}
            <div className={cn(
                "flex items-center justify-between rounded-xl border px-5 py-3.5 transition-all",
                "border-slate-200 bg-slate-50/50 group-hover:bg-slate-50 group-hover:border-slate-300",
            )}>
                <span className="text-sm font-semibold text-slate-700 group-hover:text-slate-900">
                    {product.ctaLabel}
                </span>
                <ArrowRight className="h-4 w-4 text-slate-400 transition-all group-hover:text-slate-700 group-hover:translate-x-1" />
            </div>

            {/* Subtle accent line at top */}
            <div className={cn(
                "absolute top-0 left-8 right-8 h-0.5 rounded-full opacity-0 transition-opacity group-hover:opacity-100",
                product.accentLight,
            )} />
        </Link>
    );
}
