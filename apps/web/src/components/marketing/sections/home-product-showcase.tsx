import Link from 'next/link';
import type { Route } from 'next';
import {
    ArrowRight,
    ReceiptText,
    PackageSearch,
    Wallet,
    BarChart3,
    QrCode,
    Paintbrush,
    Banknote,
    MessageSquareHeart,
    Star,
    Filter,
    TrendingUp,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SiteContainer } from '@/components/layout/site-container';
import { cn } from '@/lib/utils';

// ─── Mockups ─────────────────────────────────────────────────────────────────

function GestionMockup() {
    return (
        <div
            aria-hidden="true"
            className="w-full min-h-[340px] rounded-[2rem] border border-slate-200/70 bg-white p-6 shadow-md space-y-5 select-none overflow-hidden md:min-h-[420px] md:p-8 lg:min-h-[480px] lg:p-10"
        >
            {/* Header bar */}
            <div className="flex items-center justify-between pb-3 border-b border-slate-200/80">
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide md:text-sm">
                    Dashboard
                </span>
                <span className="text-xs text-slate-400 md:text-sm">Hoy, 1 may 2026</span>
            </div>

            {/* KPI cards */}
            <div className="grid grid-cols-2 gap-3 md:gap-4">
                <div className="rounded-2xl bg-brand-50 border border-brand-100 p-4 md:p-5 space-y-1.5">
                    <p className="text-[11px] font-medium text-brand-600 uppercase tracking-wide md:text-xs">
                        Ventas del día
                    </p>
                    <p className="text-2xl font-bold text-brand-700 md:text-[1.75rem]">$128.400</p>
                    <p className="text-[11px] text-brand-500 md:text-xs">+12% vs ayer</p>
                </div>
                <div className="rounded-2xl bg-white border border-slate-200 p-4 md:p-5 space-y-1.5">
                    <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wide md:text-xs">
                        Facturas emitidas
                    </p>
                    <p className="text-2xl font-bold text-slate-700 md:text-[1.75rem]">34</p>
                    <p className="text-[11px] text-slate-400 md:text-xs">8 pendientes</p>
                </div>
            </div>

            {/* Product list */}
            <div className="rounded-2xl bg-white border border-slate-200 divide-y divide-slate-100 overflow-hidden">
                <div className="px-4 py-3.5 flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-600 md:text-sm">Más vendidos</span>
                </div>
                {[
                    { name: 'Empanadas x12', qty: '48 uds', total: '$14.400' },
                    { name: 'Pizza muzzarella', qty: '31 uds', total: '$27.900' },
                    { name: 'Gaseosa 1.5L', qty: '22 uds', total: '$6.600' },
                ].map((item) => (
                    <div key={item.name} className="px-4 py-3 flex items-center justify-between">
                        <span className="text-xs text-slate-700 md:text-sm">{item.name}</span>
                        <div className="flex items-center gap-3 md:gap-4">
                            <span className="text-[11px] text-slate-400 md:text-xs">{item.qty}</span>
                            <span className="text-xs font-semibold text-slate-700 md:text-sm">
                                {item.total}
                            </span>
                        </div>
                    </div>
                ))}
            </div>

            {/* Stock alert */}
            <div className="rounded-2xl bg-amber-50 border border-amber-200 px-4 py-3 flex items-center gap-2.5">
                <PackageSearch className="h-4.5 w-4.5 text-amber-500 shrink-0" />
                <p className="text-xs text-amber-700 md:text-sm">
                    <span className="font-semibold">Stock bajo:</span> Harina 000 — quedan 2 kg
                </p>
            </div>
        </div>
    );
}

function CartaMockup() {
    return (
        <div
            aria-hidden="true"
            className="w-full min-h-[340px] rounded-[2rem] border border-slate-200/70 bg-white p-6 shadow-md space-y-5 select-none overflow-hidden md:min-h-[420px] md:p-8 lg:min-h-[480px] lg:p-10"
        >
            {/* QR + brand */}
            <div className="flex items-center gap-4 pb-3 border-b border-slate-200/80">
                {/* Fake QR */}
                <div className="rounded-2xl border border-slate-300 bg-white p-2.5 shrink-0">
                    <div className="w-14 h-14 md:w-16 md:h-16 grid grid-cols-4 grid-rows-4 gap-[2px]">
                        {Array.from({ length: 16 }).map((_, i) => (
                            <div
                                key={i}
                                className={cn(
                                    'rounded-[1px]',
                                    [0, 1, 4, 5, 2, 8, 10, 13, 15, 7, 11].includes(i)
                                        ? 'bg-slate-800'
                                        : 'bg-white'
                                )}
                            />
                        ))}
                    </div>
                </div>
                <div>
                    <p className="text-sm font-semibold text-slate-700">La Trattoria</p>
                    <p className="text-xs text-slate-400">mirubro.com/m/latrattoria</p>
                </div>
            </div>

            {/* Categories */}
            <div className="flex gap-2.5 overflow-hidden">
                {['Entradas', 'Pastas', 'Pizzas', 'Bebidas'].map((cat, i) => (
                    <span
                        key={cat}
                        className={cn(
                            'shrink-0 rounded-full px-3 py-1.5 text-xs font-medium',
                            i === 1
                                ? 'bg-brand-500 text-white'
                                : 'bg-white border border-slate-200 text-slate-600'
                        )}
                    >
                        {cat}
                    </span>
                ))}
            </div>

            {/* Product cards */}
            <div className="space-y-3">
                {[
                    { name: 'Tagliatelle al funghi', price: '$4.200', badge: null },
                    { name: 'Ravioles de ricotta', price: '$3.800', badge: 'Popular' },
                ].map((p) => (
                    <div
                        key={p.name}
                        className="rounded-2xl bg-white border border-slate-200 px-4 py-3 md:px-5 md:py-4 flex items-center justify-between"
                    >
                        <div>
                            <p className="text-sm font-semibold text-slate-700">{p.name}</p>
                            {p.badge && (
                                <span className="inline-block text-[10px] font-semibold text-brand-600 bg-brand-50 rounded-full px-2.5 py-0.5 mt-1">
                                    {p.badge}
                                </span>
                            )}
                        </div>
                        <span className="text-sm font-bold text-slate-700">{p.price}</span>
                    </div>
                ))}
            </div>

            {/* Propina button */}
            <div className="w-full rounded-xl bg-brand-600 text-white text-sm font-semibold py-3.5 flex items-center justify-center gap-2.5 shadow-sm">
                <Banknote className="h-4 w-4" />
                Dejar propina
            </div>
        </div>
    );
}

function ReviewsMockup() {
    return (
        <div
            aria-hidden="true"
            className="w-full min-h-[340px] rounded-[2rem] border border-slate-200/70 bg-white p-6 shadow-md space-y-5 select-none overflow-hidden md:min-h-[420px] md:p-8 lg:min-h-[480px] lg:p-10"
        >
            {/* Rating header */}
            <div className="flex items-center gap-4 pb-3 border-b border-slate-200/80">
                <div className="text-center">
                    <p className="text-4xl font-bold text-slate-800 md:text-5xl">4.8</p>
                    <div className="flex gap-0.5 justify-center mt-1">
                        {Array.from({ length: 5 }).map((_, i) => (
                            <Star
                                key={i}
                                className={cn(
                                    'h-3.5 w-3.5 md:h-4 md:w-4',
                                    i < 5 ? 'fill-amber-400 text-amber-400' : 'text-slate-300'
                                )}
                            />
                        ))}
                    </div>
                    <p className="text-xs text-slate-400 mt-1">128 reseñas</p>
                </div>

                {/* Distribution bars */}
                <div className="flex-1 space-y-1.5">
                    {[
                        { stars: 5, pct: '78%' },
                        { stars: 4, pct: '14%' },
                        { stars: 3, pct: '5%' },
                        { stars: 2, pct: '2%' },
                        { stars: 1, pct: '1%' },
                    ].map((row) => (
                        <div key={row.stars} className="flex items-center gap-2">
                            <span className="text-[10px] text-slate-500 w-4 text-right">
                                {row.stars}
                            </span>
                            <div className="flex-1 h-2 rounded-full bg-slate-200 overflow-hidden">
                                <div
                                    className="h-full rounded-full bg-amber-400"
                                    style={{ width: row.pct }}
                                />
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Recent review */}
            <div className="rounded-2xl bg-white border border-slate-200 px-4 py-3.5 space-y-2">
                <div className="flex items-center gap-2">
                    <div className="h-6 w-6 rounded-full bg-brand-100 flex items-center justify-center text-[10px] font-bold text-brand-600">
                        MG
                    </div>
                    <span className="text-sm font-semibold text-slate-700">María G.</span>
                    <div className="flex gap-0.5 ml-auto">
                        {Array.from({ length: 5 }).map((_, i) => (
                            <Star key={i} className="h-3 w-3 fill-amber-400 text-amber-400" />
                        ))}
                    </div>
                </div>
                <p className="text-xs text-slate-600 leading-relaxed md:text-sm">
                    "Excelente atención y comida, volvería sin dudarlo. Muy recomendable."
                </p>
            </div>

            {/* Origin badges */}
            <div className="flex gap-2.5 flex-wrap">
                <span className="rounded-full bg-white border border-slate-200 px-3 py-1.5 text-xs text-slate-600 font-medium">
                    Google · 94
                </span>
                <span className="rounded-full bg-brand-50 border border-brand-100 px-3 py-1.5 text-xs text-brand-600 font-medium">
                    Mi Rubro · 34
                </span>
            </div>
        </div>
    );
}

// ─── Types & data ─────────────────────────────────────────────────────────────

type Bullet = {
    icon: React.ComponentType<{ className?: string }>;
    text: string;
};

type ProductBlock = {
    id: string;
    eyebrow: string;
    title: string;
    description: string;
    bullets: Bullet[];
    ctaLabel: string;
    href: string;
    mockup: React.ComponentType;
    /** true → text left + mockup right; false → mockup left + text right */
    textFirst: boolean;
};

const BLOCKS: ProductBlock[] = [
    {
        id: 'gestion',
        eyebrow: 'Gestión Comercial',
        title: 'Todo lo que necesitás para vender, facturar y controlar tu negocio.',
        description:
            'Centralizá ventas, stock, clientes, caja y reportes en una plataforma simple para operar todos los días con más orden.',
        bullets: [
            { icon: ReceiptText, text: 'Registrá ventas y emití facturas electrónicas al instante.' },
            { icon: PackageSearch, text: 'Mantené tu stock actualizado en todos tus productos.' },
            { icon: Wallet, text: 'Controlá compras, gastos, pagos y caja desde un solo lugar.' },
            { icon: BarChart3, text: 'Accedé a reportes claros para tomar mejores decisiones.' },
        ],
        ctaLabel: 'Conocer Gestión Comercial',
        href: '/gestion',
        mockup: GestionMockup,
        textFirst: true,
    },
    {
        id: 'carta',
        eyebrow: 'Carta Online',
        title: 'Menú QR, propinas y reseñas en una experiencia digital para tu cliente.',
        description:
            'Mostrá tu carta online, actualizá productos en minutos y sumá herramientas de interacción para mejorar cada visita.',
        bullets: [
            { icon: QrCode, text: 'Publicá un menú digital accesible por QR.' },
            { icon: Paintbrush, text: 'Personalizá colores, logo, categorías e imágenes.' },
            { icon: Banknote, text: 'Recibí propinas digitales conectadas a MercadoPago.' },
            { icon: MessageSquareHeart, text: 'Conectá la experiencia con reseñas y feedback de clientes.' },
        ],
        ctaLabel: 'Conocer Carta Online',
        href: '/carta',
        mockup: CartaMockup,
        textFirst: false,
    },
    {
        id: 'resenas',
        eyebrow: 'QR Reseñas',
        title: 'Convertí cada visita en una oportunidad para mejorar tu reputación.',
        description:
            'Recolectá opiniones con QR, filtrá comentarios sensibles y potenciá tus mejores reseñas en Google.',
        bullets: [
            { icon: QrCode, text: 'Generá un QR para pedir reseñas de forma simple.' },
            { icon: Star, text: 'Redirigí clientes satisfechos a Google.' },
            { icon: Filter, text: 'Recibí feedback privado cuando algo necesita atención.' },
            { icon: TrendingUp, text: 'Medí visitas, calificaciones y evolución de la satisfacción.' },
        ],
        ctaLabel: 'Conocer QR Reseñas',
        href: '/resenas',
        mockup: ReviewsMockup,
        textFirst: true,
    },
];

// ─── Internal card ────────────────────────────────────────────────────────────

function ProductFeatureCard({
    block,
    withTopBorder,
}: {
    block: ProductBlock;
    withTopBorder: boolean;
}) {
    const Mockup = block.mockup;

    return (
        <article
            className={cn(
                'py-16 md:py-20 lg:min-h-[520px] lg:py-24',
                withTopBorder && 'border-t border-slate-200/50'
            )}
        >
            {/* Text column */}
            <div className="grid grid-cols-1 items-center gap-10 md:gap-14 lg:grid-cols-2 lg:gap-24">
                <div
                    className={cn(
                        'flex max-w-2xl flex-col justify-center space-y-8',
                        !block.textFirst && 'lg:order-last lg:ml-auto'
                    )}
                >
                    {/* Eyebrow pill */}
                    <span className="inline-flex w-fit items-center rounded-full bg-brand-50 px-4 py-2 text-sm font-semibold text-brand-700 ring-1 ring-inset ring-brand-100">
                        {block.eyebrow}
                    </span>

                    {/* Title */}
                    <h3 className="text-3xl font-bold leading-tight text-slate-900 md:text-4xl lg:text-5xl">
                        {block.title}
                    </h3>

                    {/* Description */}
                    <p className="text-base leading-8 text-slate-600 md:text-lg">{block.description}</p>

                    {/* Bullets */}
                    <ul className="space-y-5">
                        {block.bullets.map(({ icon: Icon, text }) => (
                            <li key={text} className="flex items-start gap-3">
                                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-50 ring-1 ring-inset ring-brand-100">
                                    <Icon className="h-4.5 w-4.5 text-brand-700" />
                                </span>
                                <span className="text-base text-slate-700">{text}</span>
                            </li>
                        ))}
                    </ul>

                    {/* CTA */}
                    <div className="pt-3">
                        <Button
                            asChild
                            className="h-12 rounded-xl bg-brand-600 px-7 text-base font-semibold text-white shadow-sm transition-colors hover:bg-brand-700 md:h-14"
                        >
                            <Link href={block.href as Route}>
                                {block.ctaLabel}
                                <ArrowRight className="ml-2 h-4 w-4" aria-hidden />
                            </Link>
                        </Button>
                    </div>
                </div>

                {/* Mockup column */}
                <div
                    className={cn(
                        'flex items-center',
                        !block.textFirst && 'lg:order-first'
                    )}
                >
                    <div className="w-full max-w-2xl lg:max-w-none">
                        <Mockup />
                    </div>
                </div>
            </div>
        </article>
    );
}

// ─── Section ──────────────────────────────────────────────────────────────────

export function HomeProductShowcase() {
    return (
        <section className="w-full bg-white py-20 md:py-28 lg:py-32">
            <SiteContainer>
                {/* Section header */}
                <div className="mx-auto mb-16 max-w-4xl space-y-6 text-center lg:mb-24">
                    <p className="text-sm font-semibold uppercase tracking-[0.2em] text-brand-600">
                        Una plataforma, múltiples soluciones
                    </p>
                    <h2 className="text-3xl font-bold leading-tight text-slate-900 md:text-4xl lg:text-5xl">
                        Herramientas pensadas para simplificar la gestión de tu negocio
                    </h2>
                    <p className="text-base leading-relaxed text-slate-600 lg:text-lg">
                        Desde la venta diaria hasta la experiencia digital del cliente, Mi Rubro reúne
                        las funciones clave para operar, vender y crecer con más claridad.
                    </p>
                </div>

                {/* Product blocks */}
                <div className="space-y-0">
                    {BLOCKS.map((block, index) => (
                        <ProductFeatureCard
                            key={block.id}
                            block={block}
                            withTopBorder={index > 0}
                        />
                    ))}
                </div>
            </SiteContainer>
        </section>
    );
}
