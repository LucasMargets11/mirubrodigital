import type { Metadata } from 'next';
import {
    ProductHero,
    ProductDemo,
    ProductBenefits,
    ProductSteps,
    ProductFeatures,
    ResenasPricingSection,
    ProductFinalCta,
} from '@/components/marketing/product-landing';
import {
    QrCode,
    Star,
    MessageSquareHeart,
    BarChart3,
    Smartphone,
    TrendingUp,
    Zap,
    Shield,
    Eye,
    MapPin,
} from 'lucide-react';

const SITE_URL = 'https://www.mirubro.com';

export const metadata: Metadata = {
    title: 'QR de Reseñas — Más reseñas en Google | Mi Rubro',
    description:
        'Generá un QR que lleva directo a tus reseñas de Google. Más opiniones positivas, mejor posicionamiento, cero fricción.',
    alternates: { canonical: `${SITE_URL}/resenas` },
    openGraph: {
        title: 'QR de Reseñas | Mi Rubro',
        description:
            'Un QR que lleva directo a tus reseñas de Google. Sin apps, sin fricciones.',
        url: `${SITE_URL}/resenas`,
        siteName: 'Mirubro',
        type: 'website',
        locale: 'es_AR',
    },
};

export default function ResenasPage() {
    return (
        <>
            {/* 1 ── Hero ── */}
            <ProductHero
                label="QR de Reseñas"
                title="Más reseñas en Google,"
                titleAccent="sin esfuerzo."
                subtitle="Un QR que tus clientes escanean y en un tap ya están dejando su opinión. Más reseñas, mejor rating, más clientes."
                ctaHref="/entrar"
                ctaLabel="Crear mi QR gratis"
                secondaryHref="/pricing?service=menu_qr"
                secondaryLabel="Ver planes"
                proofPoints={['Gratis para empezar', 'Link directo a Google', 'Sin apps intermedias']}
                mockup={<ResenasMockup />}
            />

            {/* 2 ── Demo visual ── */}
            <ProductDemo
                label="Flujo real"
                title="Así funciona para tu cliente"
                subtitle="Escanea → abre Google → deja su reseña. En menos de 30 segundos."
            >
                <DemoFlow />
            </ProductDemo>

            {/* 3 ── Beneficios ── */}
            <ProductBenefits
                label="Impacto"
                title="¿Por qué importan las reseñas?"
                benefits={[
                    {
                        title: 'Mejor ranking en Google',
                        description:
                            'Más reseñas recientes mejoran tu posición en Google Maps y búsquedas locales.',
                        icon: TrendingUp,
                    },
                    {
                        title: 'Confianza al instante',
                        description:
                            'Los clientes eligen negocios con buenas reseñas. Tu reputación trabaja por vos.',
                        icon: Shield,
                    },
                    {
                        title: 'Cero fricción',
                        description:
                            'Sin apps, sin formularios, sin pasos extras. Escanean y opinan.',
                        icon: Zap,
                    },
                    {
                        title: 'Feedback real',
                        description:
                            'Entendé qué les gusta a tus clientes y qué podés mejorar.',
                        icon: Eye,
                    },
                ]}
            />

            {/* 4 ── Cómo funciona ── */}
            <ProductSteps
                label="Setup"
                title="Activá tu QR en 3 pasos"
                steps={[
                    {
                        title: 'Conectá tu negocio',
                        description:
                            'Ingresá el link de tu ficha de Google My Business y listo.',
                    },
                    {
                        title: 'Descargá el QR',
                        description:
                            'Generamos un QR en alta resolución listo para imprimir.',
                    },
                    {
                        title: 'Ubicalo en tu local',
                        description:
                            'Mesas, mostrador, delivery, stickers — donde tus clientes lo vean.',
                    },
                ]}
            />

            {/* 5 ── Features ── */}
            <ProductFeatures
                label="Funciones"
                title="Simple, poderoso, sin vueltas"
                features={[
                    {
                        title: 'QR directo a Google',
                        description:
                            'Un escaneo y tu cliente ya está en la pantalla de reseñas. Sin intermediarios.',
                        icon: QrCode,
                    },
                    {
                        title: 'Optimizado para móvil',
                        description:
                            'Flujo rápido diseñado para completarse en segundos desde cualquier celular.',
                        icon: Smartphone,
                    },
                    {
                        title: 'Métricas de escaneo',
                        description:
                            'Visualizá cuántos escaneos recibís y medí el impacto en tus reseñas.',
                        icon: BarChart3,
                    },
                    {
                        title: 'Multi-ubicación',
                        description:
                            'Generá QRs diferentes para cada sucursal o punto de atención.',
                        icon: MapPin,
                    },
                    {
                        title: 'Rating promedio',
                        description:
                            'Seguí la evolución de tu rating de Google desde el panel de Mi Rubro.',
                        icon: Star,
                    },
                    {
                        title: 'Reputación en piloto automático',
                        description:
                            'Dejalo funcionando y sumá reseñas cada día sin hacer nada extra.',
                        icon: MessageSquareHeart,
                    },
                ]}
            />

            {/* 6 ── Pricing ── */}
            <ResenasPricingSection />

            {/* 7 ── CTA final ── */}
            <ProductFinalCta
                title="Tu reputación empieza con un QR"
                subtitle="Creá tu código, imprimilo y empezá a sumar reseñas hoy mismo."
                ctaHref="/entrar"
                ctaLabel="Crear mi QR"
                secondaryHref="/contacto"
                secondaryLabel="Consultar"
            />
        </>
    );
}

/* ── Mockups internos ── */

function ResenasMockup() {
    return (
        <div className="w-full max-w-xs mx-auto flex flex-col items-center gap-6">
            {/* QR Placeholder */}
            <div className="w-48 h-48 rounded-2xl border-2 border-dashed border-brand-200 bg-brand-50/30 flex items-center justify-center">
                <QrCode className="h-20 w-20 text-brand-400" />
            </div>
            {/* Stars */}
            <div className="flex gap-1">
                {Array.from({ length: 5 }).map((_, i) => (
                    <Star
                        key={i}
                        className={`h-6 w-6 ${i < 4 ? 'text-amber-400 fill-amber-400' : 'text-amber-200 fill-amber-200'}`}
                    />
                ))}
            </div>
            <p className="text-sm text-slate-500 text-center">
                4.8 de rating promedio · 127 reseñas
            </p>
        </div>
    );
}

function DemoFlow() {
    const steps = [
        { label: 'Escanea el QR', icon: QrCode },
        { label: 'Abre Google', icon: Star },
        { label: 'Deja su reseña', icon: MessageSquareHeart },
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
