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
        description: 'Inventario, ventas y caja en un solo lugar — desde el primer producto hasta la multi-sucursal.',
        features: [
            {
                title: 'Stock & Inventario',
                description: 'Control en tiempo real de productos, costos y alertas.',
                bullets: ['Tiempo real', 'Alertas de stock bajo', 'Valuación de inventario'],
                icon: Boxes
            },
            {
                title: 'Ventas / POS',
                description: 'Cobrá en mostrador o móvil con historial completo de clientes.',
                bullets: ['Ventas rápidas', 'CRM de clientes (historial)', 'Cancelaciones'],
                icon: ShoppingBag
            },
            {
                title: 'Caja',
                description: 'Aperturas y cierres guiados con arqueos por turno.',
                bullets: ['Apertura/Cierre', 'Arqueos', 'Turnos'],
                icon: Wallet
            },
            {
                title: 'Facturación & Reportes',
                description: 'Facturación electrónica, finanzas y reportes exportables.',
                bullets: ['Fact. electrónica + PDF', 'Gastos y movimientos (Pro+)', 'Exportación Excel/CSV'],
                icon: BarChart3
            },
            {
                title: 'Roles & Permisos',
                description: 'Define accesos por perfil, módulo y sucursal.',
                bullets: ['Owner/Manager/Cashier/Staff', 'Multi-sucursal (Business+)', 'Control de acceso'],
                icon: ShieldCheck,
                className: 'lg:col-span-2'
            }
        ]
    },
    {
        id: 'restaurant',
        title: 'Restaurante Inteligente',
        description: 'Orquesten salón, cocina y carta desde un solo sistema — en tiempo real, en cualquier dispositivo.',
        features: [
            {
                title: 'Órdenes & Pedidos',
                description: 'Flujo completo desde la toma hasta el cobro.',
                bullets: ['Crear/cobrar', 'Estados de orden', 'Control salón'],
                icon: ListChecks
            },
            {
                title: 'Cocina en vivo',
                description: 'Pantalla KDS con prioridades y tiempos visibles.',
                bullets: ['Pantalla cocina', 'Prioridades', 'Tiempos'],
                icon: ChefHat
            },
            {
                title: 'Mapa de mesas',
                description: 'Visualizá ocupación y rotación por turno en tiempo real.',
                bullets: ['Posición real', 'Ocupación en tiempo real', 'Asignación'],
                icon: Map
            },
            {
                title: 'Carta online QR',
                description: 'Carta pública por QR incluida, editable desde el admin.',
                bullets: ['Admin + carta pública', 'Colores/Tipografía/Logo', 'Siempre actualizada'],
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
        description: 'Tu carta digital con marca propia, fotos y analytics — sin apps, sin impresiones, sin comisiones.',
        features: [
            {
                title: 'QR y URL propios',
                description: 'URL propia y QR en alta resolución, listos para imprimir.',
                bullets: ['Subdominio propio', 'QR descargables', 'Dominio personalizado (Premium)'],
                icon: QrCode
            },
            {
                title: 'Editor de carta',
                description: 'Categorías, precios y disponibilidad desde el panel.',
                bullets: ['Categorías flexibles', 'Precios y disponibilidad', 'Destacados'],
                icon: Layers
            },
            {
                title: 'Branding personalizable',
                description: 'Colores, tipografías y logo alineados a tu marca.',
                bullets: ['Paleta propia', 'Fuentes', 'Logo en portada'],
                icon: Palette
            },
            {
                title: 'Fotos por producto',
                description: 'Mostrá cada ítem con imágenes HD.',
                bullets: ['Galería por ítem (Pro+)', 'Formatos optimizados', 'Carga masiva'],
                icon: Image
            },
            {
                title: 'Reseñas y acceso',
                description: 'Escaneás y ves al instante — con reseñas y propinas integradas.',
                bullets: ['Sin apps ni descargas', 'Reseñas de Google (Pro+)', 'Propinas Mercado Pago (Pro+)'],
                icon: Smartphone
            },
            {
                title: 'Multi-sucursal',
                description: 'Administrá múltiples cartas desde un único panel.',
                bullets: ['Cartas independientes (Premium)', 'Panel unificado', 'Edición segura'],
                icon: RefreshCw,
                className: 'lg:col-span-2'
            }
        ]
    }
];

export default function ServicesPage() {
    return (
        <div className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6 md:py-14 lg:px-8">
            <div className="flex flex-col gap-10">
                <div className="text-center space-y-4">
                    <p className="text-sm font-semibold uppercase tracking-[0.3em] text-brand-600">Servicios</p>
                    <h1 className="text-4xl font-display font-bold text-slate-900 md:text-5xl">Construido para cada vertical</h1>
                    <p className="mx-auto max-w-2xl text-lg text-slate-600">
                        Elige el servicio que mejor representa tu operación y descubre los módulos disponibles para cada flujo.
                    </p>
                </div>

                <div className="space-y-8">
                    {SERVICES.map((service) => (
                        <ServiceSection key={service.id} service={service} />
                    ))}
                </div>
            </div>
        </div>
    );
}

type ServiceSectionProps = {
    service: ServiceConfig;
};

function ServiceSection({ service }: ServiceSectionProps) {
    return (
        <section className="w-full rounded-2xl border border-slate-200 bg-white p-5 shadow-md shadow-slate-100/50 ring-1 ring-slate-100 transition-shadow md:p-6 lg:p-7">
            <div className="flex flex-col gap-6 lg:grid lg:grid-cols-[340px_1fr] lg:gap-8 lg:items-start">
                <div className="space-y-4">
                    <div className="space-y-2">
                        <p className="text-xs font-semibold uppercase tracking-[0.4em] text-brand-500">Servicio</p>
                        <h2 className="text-2xl font-display font-semibold text-slate-900 md:text-3xl">{service.title}</h2>
                        <p className="text-sm text-slate-600 md:text-base">{service.description}</p>
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
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
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
                'flex h-full flex-col border-slate-200 bg-slate-50/40 transition-all duration-200 hover:border-brand-200 hover:bg-white hover:shadow-lg hover:ring-2 hover:ring-brand-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2',
                feature.className
            )}
        >
            <CardHeader className="space-y-3 pb-3 text-center">
                <div className="mx-auto rounded-xl bg-brand-50 p-2.5 text-brand-600 shadow-inner">
                    <Icon className="h-5 w-5" aria-hidden="true" />
                </div>
                <div className="space-y-1">
                    <CardTitle className="text-base font-semibold text-slate-900">{feature.title}</CardTitle>
                    <CardDescription className="text-xs leading-relaxed text-slate-500">{feature.description}</CardDescription>
                </div>
            </CardHeader>
            <CardContent className="mt-auto pt-3">
                <ul className="space-y-1.5 text-xs text-slate-600">
                    {feature.bullets.map((bullet) => (
                        <li key={bullet} className="flex items-start gap-1.5">
                            <Check className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-brand-500" aria-hidden="true" />
                            <span>{bullet}</span>
                        </li>
                    ))}
                </ul>
            </CardContent>
        </Card>
    );
}
