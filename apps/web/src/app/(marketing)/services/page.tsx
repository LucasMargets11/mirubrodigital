import Link from 'next/link';
import { type LucideIcon, BarChart3, Boxes, Check, ChefHat, FileText, Image, Layers, ListChecks, Map, Palette, QrCode, RefreshCw, ShieldCheck, ShoppingBag, Smartphone, Wallet } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';


type ServiceVertical = 'commercial' | 'restaurant' | 'menu_qr';

type FeatureCardData = {
    title: string;
    description: string;
    bullets: string[];
    icon: LucideIcon;
    className?: string;
};

type ServiceConfig = {
    id: ServiceVertical;
    title: string;
    description: string;
    features: FeatureCardData[];
};

const SERVICE_QUERY: Record<ServiceVertical, string> = {
    commercial: 'commerce',
    restaurant: 'restaurant',
    menu_qr: 'menu_qr'
};

const SERVICES: ServiceConfig[] = [
    {
        id: 'commercial',
        title: 'Gestión Comercial',
        description: 'Controla inventario, ventas y equipo desde un único tablero pensado para retail y tiendas multi-sucursal.',
        features: [
            {
                title: 'Stock & Inventario',
                description: 'Seguimiento granular de productos, costos y movimientos.',
                bullets: ['Productos', 'Movimientos', 'Valuación'],
                icon: Boxes
            },
            {
                title: 'Ventas / POS',
                description: 'Cobrá en mostrador o móvil con tickets claros.',
                bullets: ['Ventas rápidas', 'Clientes', 'Cancelaciones'],
                icon: ShoppingBag
            },
            {
                title: 'Caja',
                description: 'Aperturas y cierres guiados para cada turno.',
                bullets: ['Apertura/Cierre', 'Arqueos', 'Turnos'],
                icon: Wallet
            },
            {
                title: 'Reportes & Métricas',
                description: 'Métricas accionables para planificar cada día.',
                bullets: ['Facturación', 'Top productos', 'Evolución'],
                icon: BarChart3
            },
            {
                title: 'Roles & Permisos',
                description: 'Define accesos por perfil y sucursal.',
                bullets: ['Owner/Manager/Cashier/Staff', 'Control de acceso'],
                icon: ShieldCheck,
                className: 'lg:col-span-2'
            }
        ]
    },
    {
        id: 'restaurant',
        title: 'Restaurantes',
        description: 'Orquesta salón, cocina y clientes en tiempo real con herramientas pensadas para operaciones gastronómicas.',
        features: [
            {
                title: 'Órdenes & Pedidos',
                description: 'Desde la toma hasta el cobro en un flujo único.',
                bullets: ['Crear/cobrar', 'Estados', 'Control salón'],
                icon: ListChecks
            },
            {
                title: 'Cocina en vivo',
                description: 'KDS con prioridades y tiempos visibles.',
                bullets: ['Pantalla cocina', 'Prioridades', 'Tiempos'],
                icon: ChefHat
            },
            {
                title: 'Mapa de mesas',
                description: 'Visualiza ocupación y rotación por turno.',
                bullets: ['Posición real', 'Ocupación', 'Asignación'],
                icon: Map
            },
            {
                title: 'Carta online QR',
                description: 'Menú editable con identidad de marca.',
                bullets: ['Subdominio', 'Colores', 'Tipografía/Logo'],
                icon: QrCode
            },
            {
                title: 'Factura/Comprobante',
                description: 'Generá y reenviá comprobantes desde cualquier dispositivo.',
                bullets: ['PDF por orden', 'Descarga', 'Historial'],
                icon: FileText,
                className: 'lg:col-span-2'
            }
        ]
    },
    {
        id: 'menu_qr',
        title: 'Menú QR Online',
        description: 'Tu carta digital siempre al día, con marca propia y sin depender de comisiones externas.',
        features: [
            {
                title: 'Carta por QR',
                description: 'URL propia y códigos QR ilimitados.',
                bullets: ['Subdominio propio', 'Multi-sucursal', 'QR descargables'],
                icon: QrCode
            },
            {
                title: 'Categorías y productos',
                description: 'Organiza cada menú como quieras.',
                bullets: ['Categorías flexibles', 'Destacados', 'Disponibilidad'],
                icon: Layers
            },
            {
                title: 'Branding personalizable',
                description: 'Colores, tipografías y logos alineados a tu marca.',
                bullets: ['Paleta propia', 'Fuentes', 'Logo en portada'],
                icon: Palette
            },
            {
                title: 'Fotos por producto',
                description: 'Mostrá variantes y combos con imágenes HD.',
                bullets: ['Galería por ítem', 'Formatos optimizados', 'Carga masiva'],
                icon: Image
            },
            {
                title: 'Acceso instantáneo',
                description: 'Sin apps ni descargas: escaneás y ves.',
                bullets: ['Compatible con todos', 'Modo oscuro', 'SEO básico'],
                icon: Smartphone
            },
            {
                title: 'Actualización en vivo',
                description: 'Cambios reflejados al instante en todos los QR.',
                bullets: ['Sin publicación manual', 'Precios dinámicos', 'Edición segura'],
                icon: RefreshCw,
                className: 'lg:col-span-2'
            }
        ]
    }
];

export default function ServicesPage() {
    return (
        <div className="flex w-full flex-col gap-16 py-10 md:py-16">
            <div className="text-center space-y-4">
                <p className="text-sm font-semibold uppercase tracking-[0.3em] text-brand-600">Servicios</p>
                <h1 className="text-4xl font-display font-bold text-slate-900 md:text-5xl">Construido para cada vertical</h1>
                <p className="mx-auto max-w-2xl text-lg text-slate-600">
                    Elige el servicio que mejor representa tu operación y descubre los módulos disponibles para cada flujo.
                </p>
            </div>

            <div className="space-y-12">
                {SERVICES.map((service) => (
                    <ServiceSection key={service.id} service={service} />
                ))}
            </div>
        </div>
    );
}

type ServiceSectionProps = {
    service: ServiceConfig;
};

function ServiceSection({ service }: ServiceSectionProps) {
    return (
        <section className="w-full rounded-3xl border border-slate-200 bg-white/90 p-6 shadow-lg shadow-slate-100 ring-1 ring-slate-100 transition-shadow md:p-8 lg:p-10">
            <div className="flex flex-col gap-6 md:gap-8 lg:gap-10 lg:grid lg:grid-cols-[minmax(280px,360px)_1fr]">
                <div className="space-y-4 lg:pr-6">
                    <div className="space-y-2">
                        <p className="text-xs font-semibold uppercase tracking-[0.4em] text-brand-500">Servicio</p>
                        <h2 className="text-3xl font-display font-semibold text-slate-900">{service.title}</h2>
                        <p className="text-base text-slate-600">{service.description}</p>
                    </div>
                    <Button
                        asChild
                        size="lg"
                        className="w-fit bg-brand-600 text-white hover:bg-brand-700 focus-visible:ring-brand-500"
                    >
                        <Link href={`/pricing?service=${SERVICE_QUERY[service.id]}`} aria-label={`Ver planes para ${service.title}`}>
                            Ver planes
                        </Link>
                    </Button>
                </div>
                <div className="w-full">
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 lg:gap-5">
                        {service.features.map((feature) => (
                            <FeatureCard key={feature.title} feature={feature} />
                        ))}
                    </div>
                </div>
            </div>
        </section>
    );
}

type FeatureCardProps = {
    feature: FeatureCardData;
};

function FeatureCard({ feature }: FeatureCardProps) {
    const Icon = feature.icon;

    return (
        <Card
            role="group"
            tabIndex={0}
            className={cn(
                'flex h-full flex-col border-slate-200 bg-slate-50/40 transition-all duration-200 hover:border-brand-200 hover:bg-white hover:shadow-xl hover:ring-2 hover:ring-brand-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2',
                feature.className
            )}
        >
            <CardHeader className="space-y-4 pb-0 text-center">
                <div className="mx-auto rounded-2xl bg-brand-50 p-3 text-brand-600 shadow-inner">
                    <Icon className="h-6 w-6" aria-hidden="true" />
                </div>
                <div className="space-y-1">
                    <CardTitle className="text-lg text-slate-900">{feature.title}</CardTitle>
                    <CardDescription className="text-sm text-slate-500">{feature.description}</CardDescription>
                </div>
            </CardHeader>
            <CardContent className="mt-auto pt-6">
                <ul className="space-y-2 text-sm text-slate-600">
                    {feature.bullets.map((bullet) => (
                        <li key={bullet} className="flex items-start gap-2">
                            <Check className="mt-0.5 h-4 w-4 text-brand-500" aria-hidden="true" />
                            <span>{bullet}</span>
                        </li>
                    ))}
                </ul>
            </CardContent>
        </Card>
    );
}
