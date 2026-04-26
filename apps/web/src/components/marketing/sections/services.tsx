import Link from 'next/link';
import { ArrowRight, Check, Store, BarChart3, QrCode } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { SiteContainer } from '@/components/layout/site-container';

const SOLUTIONS_CARDS = [
    {
        id: 'plan-basic',
        title: 'Plan Basic · Gestión Comercial',
        description: 'Ideal para negocios que buscan ordenar su operación diaria.',
        icon: Store,
        features: [
            'Ventas, stock y caja en una sola plataforma',
            'Gestión simple y rápida para el día a día',
            'Control de productos y movimientos',
            'Reportes claros para tomar decisiones'
        ],
        ctaLabel: 'Conocer Plan Basic',
        ctaHref: '/gestion',
    },
    {
        id: 'plan-pro',
        title: 'Plan Pro · Gestión Comercial',
        description: 'Pensado para negocios que necesitan más control, escalabilidad y eficiencia.',
        icon: BarChart3,
        features: [
            'Todo lo del Plan Basic en una solución más robusta',
            'Multi-caja y gestión avanzada de stock',
            'Compras, proveedores y reportes más completos',
            'Mayor visibilidad del negocio en tiempo real'
        ],
        ctaLabel: 'Conocer Plan Pro',
        ctaHref: '/gestion',
    },
    {
        id: 'menu-qr',
        title: 'Menú QR Online + Reseñas + Propina',
        description: 'Una experiencia digital pensada para mejorar la atención y potenciar cada visita.',
        icon: QrCode,
        features: [
            'Menú digital online accesible por QR',
            'Actualización inmediata de productos y precios',
            'Reseñas para generar confianza y reputación',
            'Opción de propina digital'
        ],
        ctaLabel: 'Ver Menú QR',
        ctaHref: '/carta',
    }
];

export function ServicesSection() {
    return (
        <section className="bg-slate-50 py-16 lg:py-24" id="servicios">
            <SiteContainer>
                {/* Section Header */}
                <div className="mx-auto max-w-2xl text-center mb-16">
                    <h2 className="text-3xl font-display font-bold text-slate-900 tracking-tight sm:text-4xl">
                        Soluciones pensadas para cada etapa de tu negocio
                    </h2>
                    <p className="mt-4 text-lg text-slate-600">
                        Elegí el plan o la herramienta ideal para vender más, ordenar tu operación y mejorar la experiencia de tus clientes.
                    </p>
                </div>

                {/* Services Grid */}
                <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-3">
                    {SOLUTIONS_CARDS.map((service) => {
                        const Icon = service.icon;

                        return (
                            <Card 
                                key={service.id} 
                                className="flex flex-col h-full border-slate-200 bg-white shadow-sm transition-all duration-300 hover:shadow-lg hover:border-brand-200 relative overflow-hidden group"
                            >
                                <CardHeader className="pb-4 relative z-10">
                                    <div className="w-12 h-12 rounded-xl flex items-center justify-center mb-4 transition-colors bg-slate-100 text-slate-600 group-hover:bg-brand-50 group-hover:text-brand-600">
                                        <Icon className="w-6 h-6" strokeWidth={1.5} />
                                    </div>
                                    <h3 className="text-xl font-bold text-slate-900 leading-snug">
                                        {service.title}
                                    </h3>
                                </CardHeader>

                                <CardContent className="flex-1 pb-6 relative z-10">
                                    <p className="text-slate-600 mb-6 leading-relaxed">
                                        {service.description}
                                    </p>
                                    
                                    <ul className="space-y-3">
                                        {service.features.map((feature, idx) => (
                                            <li key={idx} className="flex items-start gap-3 text-sm text-slate-700">
                                                <div className="mt-0.5 min-w-4 flex text-brand-500">
                                                    <Check className="w-4 h-4" strokeWidth={2.5} />
                                                </div>
                                                <span>{feature}</span>
                                            </li>
                                        ))}
                                    </ul>
                                </CardContent>

                                <CardFooter className="pt-0 pb-6 mt-auto relative z-10">
                                    <Button 
                                        asChild 
                                        variant="outline"
                                        className="w-full justify-between group/btn border-slate-200 text-slate-700 hover:text-brand-700 hover:border-brand-200 hover:bg-brand-50/50 transition-all shadow-sm"
                                    >
                                        <Link href={service.ctaHref as any}>
                                            <span className="font-semibold">{service.ctaLabel}</span>
                                            <ArrowRight className="w-4 h-4 ml-2 transition-transform group-hover/btn:translate-x-1" />
                                        </Link>
                                    </Button>
                                </CardFooter>
                            </Card>
                        );
                    })}
                </div>
            </SiteContainer>
        </section>
    );
}
