import type { Metadata } from 'next';
import {
    ProductHero,
    ProductDemo,
    ProductBenefits,
    ProductSteps,
    ProductFeatures,
    ResenasPricingSection,
    ResenasPosterSection,
    ProductFinalCta,
} from '@/components/marketing/product-landing';
import NextImage from 'next/image';
import {
    QrCode,
    Star,
    MessageSquareHeart,
    BarChart3,
    Smartphone,
    TrendingUp,
    MapPin,
    Filter,
} from 'lucide-react';
import { PRODUCT, PRODUCT_BENEFITS } from '@/features/reviews/product';

const SITE_URL = 'https://www.mirubro.com';

export const metadata: Metadata = {
    title: 'QR de Reseñas — Más reseñas en Google + feedback interno | Mi Rubro',
    description:
        'Un QR inteligente que filtra: las opiniones altas van directo a Google y las bajas quedan como feedback privado para que mejores tu servicio.',
    alternates: { canonical: `${SITE_URL}/resenas` },
    openGraph: {
        title: 'QR de Reseñas | Mi Rubro',
        description:
            'Un QR inteligente que lleva las buenas opiniones a Google y captura el feedback privado para tu negocio.',
        url: `${SITE_URL}/resenas`,
        siteName: 'Mirubro',
        type: 'website',
        locale: 'es_AR',
    },
    twitter: {
        card: 'summary_large_image',
        title: 'QR de Reseñas | Mi Rubro',
        description:
            'Un QR inteligente que filtra opiniones: las altas a Google, las bajas como feedback privado.',
    },
};

export default function ResenasPage() {
    return (
        <>
            {/* JSON-LD: SoftwareApplication */}
            <script
                type="application/ld+json"
                dangerouslySetInnerHTML={{
                    __html: JSON.stringify({
                        '@context': 'https://schema.org',
                        '@type': 'SoftwareApplication',
                        name: 'Mirubro QR de Reseñas',
                        description:
                            'Un QR inteligente que filtra: las opiniones altas van directo a Google y las bajas quedan como feedback privado para que mejores tu servicio.',
                        url: `${SITE_URL}/resenas`,
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
                label="Reputación en Google Maps"
                titlePrimary="Reseñas que inspiran confianza."
                titleSecondary="Tu negocio gana visibilidad."
                subtitle="Impulsá tu perfil con opiniones reales, mejor valoración e imágenes de tus clientes para fortalecer tu presencia en Google Maps y generar nuevas oportunidades de venta."
                ctaHref="/entrar"
                ctaLabel="Impulsar mi perfil"
                secondaryHref="#planes-resenas"
                secondaryLabel="Ver planes"
                proofPoints={['Visibilidad local', 'Reputación online', 'Consultas calificadas']}
                mockup={
                    <NextImage
                        src="/images/mockupopinion.png"
                        alt="Vista previa del QR de Reseñas Mi Rubro"
                        width={600}
                        height={450}
                        className="w-full max-w-md h-auto"
                        priority
                    />
                }
            />

            {/* 2 ── Demo visual ── */}
            <ProductDemo
                label="Flujo real"
                title="Así funciona para tu cliente"
                subtitle="Escanea → califica → el sistema decide: Google o feedback privado. En menos de 30 segundos."
            >
                <DemoFlow />
            </ProductDemo>

            {/* 3 ── Beneficios ── */}
            <ProductBenefits
                label="Resultados"
                title="¿Qué lográs con QR de Reseñas?"
                subtitle="Convertí cada buena experiencia en más visibilidad, más confianza y nuevas oportunidades de venta para tu negocio."
                benefits={[
                    {
                        title: 'Mejorás tu visibilidad en Google Maps',
                        description:
                            'Cada reseña positiva fortalece la presencia digital de tu negocio y aumenta las chances de aparecer mejor posicionado cuando alguien busca opciones como la tuya.',
                        icon: MapPin,
                    },
                    {
                        title: 'Generás confianza antes del primer contacto',
                        description:
                            'Las buenas calificaciones y comentarios reales transmiten credibilidad, reducen dudas y ayudan a que más personas te elijan frente a otras opciones.',
                        icon: Star,
                    },
                    {
                        title: 'Llegás a más clientes con mejor reputación',
                        description:
                            'Una ficha bien valorada atrae más visitas desde búsquedas locales y convierte esa visibilidad en consultas, visitas al local y nuevas ventas.',
                        icon: TrendingUp,
                    },
                ]}
            />

            {/* 4 ── Carteles para tu local ── */}
            <ResenasPosterSection />

            {/* 5 ── Cómo funciona ── */}
            <ProductSteps
                label="Setup"
                title="Activá tu QR en 3 pasos"
                steps={[
                    {
                        title: 'Conectá tu negocio',
                        description:
                            'Ingresá el link de tu ficha de Google y definí el umbral de redirección (ej: ≥4★ → Google).',
                    },
                    {
                        title: 'Descargá el QR',
                        description:
                            'Generamos un QR en alta resolución listo para imprimir o compartir digitalmente.',
                    },
                    {
                        title: 'Ubicalo en tu local',
                        description:
                            'Mesas, mostrador, delivery — tus clientes opinan y el sistema filtra automáticamente.',
                    },
                ]}
            />

            {/* 5 ── Features ── */}
            <ProductFeatures
                label="Funciones"
                title="Simple, poderoso, sin vueltas"
                features={[
                    {
                        title: 'Filtrado inteligente',
                        description:
                            'Las calificaciones altas van a Google y las bajas quedan como feedback privado. Vos definís el umbral.',
                        icon: Filter,
                    },
                    {
                        title: 'QR con redirección automática',
                        description:
                            'Un escaneo y tu cliente ya está opinando. El sistema decide el destino según su calificación.',
                        icon: QrCode,
                    },
                    {
                        title: 'Optimizado para móvil',
                        description:
                            'Flujo rápido diseñado para completarse en segundos desde cualquier celular.',
                        icon: Smartphone,
                    },
                    {
                        title: 'Analítica de conversión',
                        description:
                            'Visualizá escaneos, conversión, distribución de estrellas y pipeline operativo.',
                        icon: BarChart3,
                    },
                    {
                        title: 'Multi-ubicación',
                        description:
                            'Generá QRs diferentes para cada sucursal o punto de atención.',
                        icon: MapPin,
                    },
                    {
                        title: 'Reputación en piloto automático',
                        description:
                            'Dejalo funcionando y sumá reseñas cada día sin hacer nada extra.',
                        icon: MessageSquareHeart,
                    },
                ]}
            />

            {/* 7 ── Pricing ── */}
            <div id="planes-resenas" className="scroll-mt-20">
                <ResenasPricingSection />
            </div>

            {/* 7 ── CTA final ── */}
            <ProductFinalCta
                title="Tu reputación empieza con un QR"
                subtitle="Compartí tu QR con tus clientes y empezá a sumar reseñas hoy mismo."
                ctaHref="/entrar"
                ctaLabel="Compartir mi QR"
                secondaryHref="/contacto"
                secondaryLabel="Consultar"
            />
        </>
    );
}

/* ── Mockups internos ── */


function DemoFlow() {
    const steps = [
        { label: 'Escanea el QR', icon: QrCode },
        { label: 'Califica y opina', icon: Star },
        { label: 'Filtrado inteligente', icon: Filter },
        { label: 'Google o feedback', icon: MessageSquareHeart },
    ];

    return (
        <div className="absolute inset-0 flex items-center justify-center p-6">
            <div className="flex flex-col md:flex-row items-center gap-8 md:gap-12">
                {steps.map((step, i) => {
                    const Icon = step.icon;
                    return (
                        <div key={step.label} className="flex flex-col items-center gap-3">
                            <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-white border border-slate-200 shadow-sm">
                                <Icon className="h-8 w-8 text-brand-500" />
                            </div>
                            <p className="text-sm font-medium text-slate-700">{step.label}</p>
                            {i < steps.length - 1 && (
                                <div className="hidden md:block absolute" style={{ left: `${33 * (i + 1)}%` }}>
                                    {/* Arrow between steps handled by gap */}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
