import type { Metadata } from 'next';
import {
    ProductHero,
    ProductBenefits,
    ProductSteps,
    ProductFeatures,
    GestionPricingSection,
    ProductFinalCta,
} from '@/components/marketing/product-landing';
import { SiteContainer } from '@/components/layout/site-container';
import NextImage from 'next/image';
import {
    ShoppingBag,
    Boxes,
    BarChart3,
    Wallet,
    FileText,
    ShieldCheck,
    TrendingUp,
    Clock,
    Eye,
    Users2,
    Layers,
    Zap,
} from 'lucide-react';

const SITE_URL = 'https://www.mirubro.com';

export const metadata: Metadata = {
    title: 'Gestión Comercial — Ventas, Stock y Caja | Mi Rubro',
    description:
        'Controlá ventas, inventario, caja y facturación desde una sola plataforma. Diseñada para comercios que necesitan orden y visibilidad real.',
    alternates: { canonical: `${SITE_URL}/gestion` },
    openGraph: {
        title: 'Gestión Comercial | Mi Rubro',
        description:
            'Ventas, stock, caja y facturación centralizados para tu comercio.',
        url: `${SITE_URL}/gestion`,
        siteName: 'Mirubro',
        type: 'website',
        locale: 'es_AR',
    },
    twitter: {
        card: 'summary_large_image',
        title: 'Gestión Comercial | Mi Rubro',
        description:
            'Controlá ventas, inventario, caja y facturación desde una sola plataforma.',
    },
};

export default function GestionPage() {
    return (
        <>
            {/* JSON-LD: SoftwareApplication */}
            <script
                type="application/ld+json"
                dangerouslySetInnerHTML={{
                    __html: JSON.stringify({
                        '@context': 'https://schema.org',
                        '@type': 'SoftwareApplication',
                        name: 'Mirubro Gestión Comercial',
                        description:
                            'Controlá ventas, inventario, caja y facturación desde una sola plataforma. Diseñada para comercios que necesitan orden y visibilidad real.',
                        url: `${SITE_URL}/gestion`,
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
                label="Gestión Comercial para Crecer"
                titlePrimary="Ordená la operación diaria."
                titleSecondary="Tomá decisiones rentables."
                subtitle="Centralizá ventas, stock, caja y facturación para reducir errores, ordenar el día a día y entender qué pasa en tu negocio con información real."
                ctaHref="/entrar"
                ctaLabel="Probar gratis"
                secondaryHref="/pricing?service=commerce"
                secondaryLabel="Ver planes"
                proofPoints={['Stock bajo control', 'Operación ordenada', 'Datos para decidir']}
                mockup={<GestionMockup />}
            />

            {/* 2 ── Demo visual ── */}
            <section className="py-16 lg:py-24">
                <SiteContainer>
                    <div className="space-y-10">
                        <div className="text-center max-w-2xl mx-auto space-y-3">
                            <p className="text-sm font-semibold uppercase tracking-[0.25em] text-brand-600">
                                En acción
                            </p>
                            <h2 className="text-3xl font-display font-bold text-slate-900">
                                Así se ve tu operación diaria
                            </h2>
                            <p className="text-lg text-slate-600">
                                Un panel pensado para que tu equipo venda rápido y vos tengas control total.
                            </p>
                        </div>

                        <div className="mx-auto max-w-5xl">
                            <NextImage
                                src="/images/mockdesk1.png"
                                alt="Panel de Gestión Comercial Mi Rubro"
                                width={1536}
                                height={1024}
                                quality={90}
                                className="w-full h-auto rounded-lg"
                                sizes="(max-width: 768px) 95vw, 1024px"
                                priority
                            />
                        </div>
                    </div>
                </SiteContainer>
            </section>

            {/* 3 ── Beneficios ── */}
            <ProductBenefits
                label="Resultados"
                title="Lo que cambia cuando ordenás tu negocio"
                benefits={[
                    {
                        title: 'Vendé más rápido',
                        description:
                            'Punto de venta ágil con accesos directos, combos y múltiples medios de pago.',
                        icon: Zap,
                    },
                    {
                        title: 'Nunca más sin stock',
                        description:
                            'Alertas automáticas de stock mínimo, reposición a proveedores y trazabilidad total.',
                        icon: Eye,
                    },
                    {
                        title: 'Caja siempre cuadrada',
                        description:
                            'Arqueos guiados, control de egresos y auditoría por turno para cada caja.',
                        icon: Wallet,
                    },
                    {
                        title: 'Decisiones con datos',
                        description:
                            'Reportes de ventas, márgenes y KPIs en tiempo real desde el panel.',
                        icon: TrendingUp,
                    },
                    {
                        title: 'Tu equipo autónomo',
                        description:
                            'Roles y permisos granulares para vendedores, cajeros y gerentes.',
                        icon: Users2,
                    },
                ]}
            />

            {/* 4 ── Cómo funciona ── */}
            <ProductSteps
                label="Implementación"
                title="Arrancá en 3 pasos"
                steps={[
                    {
                        title: 'Creá tu negocio',
                        description:
                            'Registrate y configurá tu marca, sucursales y roles con un onboarding guiado.',
                    },
                    {
                        title: 'Cargá tus productos',
                        description:
                            'Importá tu catálogo con CSV o cargá manualmente con presets por rubro.',
                    },
                    {
                        title: 'Vendé y medí',
                        description:
                            'Activá cajas, cobrá y empezá a ver métricas al instante.',
                    },
                ]}
            />

            {/* 5 ── Features ── */}
            <ProductFeatures
                label="Funciones"
                title="Todo lo que necesitás para operar"
                features={[
                    {
                        title: 'Punto de venta',
                        description:
                            'Ventas rápidas con búsqueda, combos, descuentos y múltiples medios de pago.',
                        icon: ShoppingBag,
                    },
                    {
                        title: 'Inventario & Stock',
                        description:
                            'Movimientos, alertas de mínimo, valuación y ajustes masivos.',
                        icon: Boxes,
                    },
                    {
                        title: 'Caja & Turnos',
                        description:
                            'Apertura/cierre guiado, control de diferencias y múltiples cajas por sucursal.',
                        icon: Wallet,
                    },
                    {
                        title: 'Reportes & BI',
                        description:
                            'Dashboards con KPIs diarios, históricos y exportación a Excel/CSV.',
                        icon: BarChart3,
                    },
                    {
                        title: 'Facturación electrónica',
                        description:
                            'Facturas, notas de crédito/débito y reportes de IVA integrados con AFIP.',
                        icon: FileText,
                    },
                    {
                        title: 'Multi-sucursal',
                        description:
                            'Gestión centralizada de sucursales, roles y métricas consolidadas.',
                        icon: Layers,
                    },
                ]}
            />

            {/* 6 ── Pricing ── */}
            <GestionPricingSection />

            {/* 7 ── CTA final ── */}
            <ProductFinalCta
                title="¿Listo para ordenar tu negocio?"
                subtitle="Creá tu cuenta gratis y empezá a vender en minutos."
                ctaHref="/entrar"
                ctaLabel="Empezar ahora"
                secondaryHref="/contacto"
                secondaryLabel="Hablar con ventas"
            />
        </>
    );
}

/* ── Mockups internos ── */

function GestionMockup() {
    return (
        <div className="w-full max-w-md aspect-[4/3] rounded-xl border border-slate-200 bg-white shadow-xl overflow-hidden">
            {/* Browser bar */}
            <div className="h-7 bg-slate-50 border-b border-slate-100 flex items-center gap-1.5 px-3">
                <div className="flex gap-1.5">
                    <div className="w-2.5 h-2.5 rounded-full bg-red-400/20 border border-red-500/30" />
                    <div className="w-2.5 h-2.5 rounded-full bg-amber-400/20 border border-amber-500/30" />
                    <div className="w-2.5 h-2.5 rounded-full bg-emerald-400/20 border border-emerald-500/30" />
                </div>
                <div className="ml-4 flex-1 h-4 bg-white rounded-md border border-slate-100 max-w-[140px]" />
            </div>
            {/* Dashboard screenshot */}
            <div className="relative w-full h-[calc(100%-1.75rem)] overflow-hidden bg-slate-50">
                <NextImage
                    src="/images/masmockupdesktop.png"
                    alt="Vista previa del panel de Gestión Comercial Mi Rubro"
                    fill
                    className="object-cover object-top"
                    sizes="(max-width: 768px) 90vw, 448px"
                    priority
                />
            </div>
        </div>
    );
}

function DemoDashboard() {
    return (
        <div className="absolute inset-0 flex items-center justify-center p-6">
            <div className="w-full h-full grid grid-cols-4 gap-4">
                {/* Sidebar */}
                <div className="col-span-1 bg-white rounded-lg border border-slate-100 p-3 hidden md:flex flex-col gap-2">
                    {Array.from({ length: 6 }).map((_, i) => (
                        <div
                            key={i}
                            className={`h-8 rounded ${i === 0 ? 'bg-brand-50 border border-brand-100' : 'bg-slate-50'}`}
                        />
                    ))}
                </div>
                {/* Main */}
                <div className="col-span-4 md:col-span-3 flex flex-col gap-4">
                    {/* KPI row */}
                    <div className="grid grid-cols-3 gap-3">
                        {['Ventas hoy', 'Ticket promedio', 'Unidades'].map((label) => (
                            <div
                                key={label}
                                className="bg-white rounded-lg border border-slate-100 p-3 flex flex-col justify-between"
                            >
                                <span className="text-[10px] text-slate-400 uppercase tracking-wider">{label}</span>
                                <span className="text-lg font-bold text-slate-800 mt-1">—</span>
                            </div>
                        ))}
                    </div>
                    {/* Chart area */}
                    <div className="flex-1 bg-white rounded-lg border border-slate-100 p-4 flex items-end gap-1">
                        {[40, 65, 45, 80, 60, 90, 55, 70, 85, 50, 75, 95].map((h, i) => (
                            <div
                                key={i}
                                className="flex-1 bg-brand-100 rounded-t"
                                style={{ height: `${h}%` }}
                            />
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}
