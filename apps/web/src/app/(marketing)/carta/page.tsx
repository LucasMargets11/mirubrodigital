import type { Metadata } from 'next';
import {
    ProductHero,
    ProductDemo,
    ProductBenefits,
    ProductSteps,
    ProductFeatures,
    CartaPricingSection,
    ProductFinalCta,
} from '@/components/marketing/product-landing';
import NextImage from 'next/image';
import {
    QrCode,
    Palette,
    Layers,
    Image,
    Smartphone,
    RefreshCw,
    Zap,
    Eye,
    PenLine,
    Globe,
    Star,
    BadgeDollarSign,
} from 'lucide-react';

const SITE_URL = 'https://www.mirubro.com';

export const metadata: Metadata = {
    title: 'Carta Online — Menú Digital QR | Mi Rubro',
    description:
        'Publicá tu carta digital con QR propio, fotos HD y branding personalizado. Sin apps, sin comisiones, siempre actualizada.',
    alternates: { canonical: `${SITE_URL}/carta` },
    openGraph: {
        title: 'Carta Online — Menú Digital QR | Mi Rubro',
        description:
            'Tu carta digital con marca propia, QR y actualización al instante.',
        url: `${SITE_URL}/carta`,
        siteName: 'Mirubro',
        type: 'website',
        locale: 'es_AR',
    },
    twitter: {
        card: 'summary_large_image',
        title: 'Carta Online — Menú Digital QR | Mi Rubro',
        description:
            'Publicá tu carta digital con QR propio, fotos HD y branding personalizado.',
    },
};

export default function CartaPage() {
    return (
        <>
            {/* JSON-LD: SoftwareApplication */}
            <script
                type="application/ld+json"
                dangerouslySetInnerHTML={{
                    __html: JSON.stringify({
                        '@context': 'https://schema.org',
                        '@type': 'SoftwareApplication',
                        name: 'Mirubro Carta Online',
                        description:
                            'Publicá tu carta digital con QR propio, fotos HD y branding personalizado. Sin apps, sin comisiones, siempre actualizada.',
                        url: `${SITE_URL}/carta`,
                        applicationCategory: 'BusinessApplication',
                        operatingSystem: 'Web',
                        offers: {
                            '@type': 'Offer',
                            price: '0',
                            priceCurrency: 'ARS',
                            description: 'Prueba gratuita disponible',
                        },
                        publisher: {
                            '@type': 'Organization',
                            name: 'Mirubro',
                            url: SITE_URL,
                        },
                    }),
                }}
            />

            {/* 1 ── Hero ── */}
            <ProductHero
                label="Carta Online para Vender Mejor"
                titlePrimary="Mostrá mejor tus productos."
                titleSecondary="Facilitá cada pedido."
                subtitle="Creá una carta visual, actualizada y fácil de usar desde el celular para que tus clientes descubran tus productos, elijan con facilidad y disfruten una mejor experiencia."
                ctaHref="/entrar"
                ctaLabel="Crear mi carta gratis"
                secondaryHref="/pricing?service=menu_qr"
                secondaryLabel="Ver planes"
                proofPoints={['Productos con fotos', 'Precios al día', 'Experiencia en mesa']}
                mockup={
                    <NextImage
                        src="/images/mockcarta.png"
                        alt="Vista previa de Carta Online Mi Rubro"
                        width={600}
                        height={450}
                        quality={90}
                        className="w-full max-w-md h-auto"
                        priority
                    />
                }
            />

            {/* 2 ── Demo visual ── */}
            <ProductDemo
                label="Vista previa"
                title="Así lo ven tus clientes"
                subtitle="Escanean el QR y acceden a tu carta completa, con fotos y precios actualizados."
            >
                <DemoMenu />
            </ProductDemo>

            {/* 3 ── Beneficios ── */}
            <ProductBenefits
                label="Ventajas"
                title="¿Por qué una carta digital?"
                benefits={[
                    {
                        title: 'Actualizá al instante',
                        description:
                            'Cambiá precios, agregá platos o marcá como no disponible en segundos, sin reimprimir.',
                        icon: Zap,
                    },
                    {
                        title: 'Mejor experiencia',
                        description:
                            'Fotos HD, categorías claras y navegación rápida desde cualquier celular.',
                        icon: Eye,
                    },
                    {
                        title: 'Tu marca, siempre',
                        description:
                            'Personalizá colores, tipografía y logo para que se sienta 100% tuyo.',
                        icon: Palette,
                    },
                    {
                        title: 'Sin costos por venta',
                        description:
                            'Sin comisiones por transacción ni suscripciones ocultas.',
                        icon: BadgeDollarSign,
                    },
                ]}
            />

            {/* 4 ── Cómo funciona ── */}
            <ProductSteps
                label="Setup"
                title="Publicá tu carta en 3 pasos"
                steps={[
                    {
                        title: 'Cargá tus productos',
                        description:
                            'Creá categorías, agregá platos con fotos y describí cada ítem.',
                    },
                    {
                        title: 'Personalizá tu marca',
                        description:
                            'Elegí colores, tipografía y subí tu logo para una carta 100% propia.',
                    },
                    {
                        title: 'Compartí el QR',
                        description:
                            'Descargá el QR en alta resolución y ponelo en mesas, mostrador o redes.',
                    },
                ]}
            />

            {/* 5 ── Features ── */}
            <ProductFeatures
                label="Funciones"
                title="Todo lo que incluye tu carta digital"
                features={[
                    {
                        title: 'QR y URL propios',
                        description:
                            'Subdominio personalizado y QR descargable en alta resolución.',
                        icon: QrCode,
                    },
                    {
                        title: 'Editor de carta',
                        description:
                            'Gestioná categorías, precios, disponibilidad y destacados desde el panel.',
                        icon: PenLine,
                    },
                    {
                        title: 'Branding personalizable',
                        description:
                            'Colores, tipografías y logo alineados a tu identidad de marca.',
                        icon: Palette,
                    },
                    {
                        title: 'Fotos por producto',
                        description:
                            'Mostrá cada ítem con imágenes HD, galería y carga masiva.',
                        icon: Image,
                    },
                    {
                        title: 'Acceso universal',
                        description:
                            'Funciona en cualquier celular sin descargar apps. Un click y listo.',
                        icon: Globe,
                    },
                    {
                        title: 'Multi-sucursal',
                        description:
                            'Administrá múltiples cartas desde un único panel centralizado.',
                        icon: RefreshCw,
                    },
                ]}
            />

            {/* 6 ── Pricing ── */}
            <CartaPricingSection />

            {/* 7 ── CTA final ── */}
            <ProductFinalCta
                title="Tu carta digital lista en minutos"
                subtitle="Creá tu cuenta, cargá productos y compartí el QR con tus clientes."
                ctaHref="/entrar"
                ctaLabel="Empezar gratis"
                secondaryHref="/contacto"
                secondaryLabel="Consultar"
            />
        </>
    );
}

/* ── Mockups internos ── */


function DemoMenu() {
    const items = [
        { name: 'Milanesa napolitana', price: '$6.500', cat: 'Platos principales' },
        { name: 'Ensalada César', price: '$4.200', cat: 'Ensaladas' },
        { name: 'Lomo al verdeo', price: '$8.900', cat: 'Platos principales' },
        { name: 'Brownie con helado', price: '$3.800', cat: 'Postres' },
    ];

    return (
        <div className="absolute inset-0 flex items-center justify-center p-6">
            <div className="w-full max-w-lg mx-auto space-y-4">
                {/* Header */}
                <div className="text-center space-y-1">
                    <div className="w-12 h-12 mx-auto rounded-full bg-brand-50 border border-brand-100" />
                    <p className="text-sm font-semibold text-slate-700">Mi Restaurante</p>
                    <div className="flex gap-2 justify-center">
                        {['Todos', 'Platos', 'Ensaladas', 'Postres'].map((cat, i) => (
                            <span
                                key={cat}
                                className={`text-xs px-3 py-1 rounded-full border ${
                                    i === 0 ? 'bg-brand-50 border-brand-200 text-brand-700' : 'bg-white border-slate-200 text-slate-500'
                                }`}
                            >
                                {cat}
                            </span>
                        ))}
                    </div>
                </div>
                {/* Items */}
                <div className="grid grid-cols-2 gap-3">
                    {items.map((item) => (
                        <div key={item.name} className="bg-white rounded-lg border border-slate-100 p-3 space-y-1">
                            <div className="w-full h-14 bg-slate-100 rounded" />
                            <p className="text-xs font-medium text-slate-700 truncate">{item.name}</p>
                            <p className="text-xs font-bold text-brand-600">{item.price}</p>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
