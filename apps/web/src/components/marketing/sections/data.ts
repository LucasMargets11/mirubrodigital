import { LucideIcon, BarChart3, Boxes, Building2, Layers, QrCode, ShieldCheck, ShoppingBag, Users2, Store, Receipt, Smartphone } from 'lucide-react';

export type FeatureItem = {
    title: string;
    description: string;
    icon: LucideIcon;
};

export type ServiceItem = {
    id: string;
    title: string;
    description: string;
    features: string[];
    icon: LucideIcon;
    ctaLabel: string;
    ctaHref: string;
    highlight?: boolean;
};

export type IndustryItem = {
    id: 'restaurantes' | 'comercios' | 'servicios';
    label: string;
    description: string;
    bullets: string[];
    highlight: string;
};

export type PlanItem = {
    name: string;
    tagline: string;
    priceNote: string;
    bullets: string[];
    ctaLabel: string;
};

export const HERO_PROOF_POINTS = ['Sin tarjeta', 'Multi-tenant', 'Setup en minutos'];

export const TRUST_LOGOS = ['Manzana Group', 'La Pizza', 'Retail Hub', 'Foodtruck Co.', 'Bar Central', 'Mercado 24/7'];

export const PAIN_POINTS = ['Caja dispersa y sin control', 'Stock sin visibilidad en tiempo real', 'Ventas que no se consolidan', 'Reportes lentos y poco claros', 'Mesas, salón y delivery desconectados'];

export const SOLUTIONS = ['Métricas accionables en un solo panel', 'Roles y permisos para cada área', 'Multi-sucursal listo para escalar', 'Trazabilidad y auditoría automática', 'Integraciones con canales digitales'];

export const SERVICES: ServiceItem[] = [
    {
        id: 'gestion-comercial',
        title: 'Gestión Comercial & POS',
        description: 'Todo lo que necesitás para operar: control de ventas, stock, cajas y equipos, centralizado en una sola plataforma.',
        icon: Store,
        features: [
            'Punto de venta multi-caja rápido',
            'Control de stock en tiempo real',
            'Gestión de proveedores y compras',
            'Reportes y Business Intelligence',
        ],
        ctaLabel: 'Ver detalles',
        ctaHref: '/gestion',
        highlight: true,
    },
    {
        id: 'menu-qr',
        title: 'Menú Digital & QR',
        description: 'La carta inteligente que tus clientes aman. Autogestión de pedidos directo a cocina sin comisiones por venta.',
        icon: QrCode,
        features: [
            'Pedidos directo a cocina/barra',
            'Actualización de precios al instante',
            'Sin comisiones por transacción',
            'Personalización total de marca',
        ],
        ctaLabel: 'Ver demo',
        ctaHref: '/menu',
    },
    {
        id: 'facturacion',
        title: 'Facturación y Finanzas',
        description: 'Automatizá tu administración. Emití facturas fiscales en segundos y mantené tus cuentas claras sin esfuerzo.',
        icon: Receipt,
        features: [
            'Factura Electrónica integrada (AFIP/SAT)',
            'Cuentas corrientes de clientes',
            'Conciliación de caja automática',
            'Centro de costos y gastos',
        ],
        ctaLabel: 'Conocer más',
        ctaHref: '/facturacion',
    },
];

export const FEATURES: FeatureItem[] = [
    {
        title: 'Punto de venta rápido',
        description: 'Ventas ágiles con accesos directos, combos y usuarios concurrentes.',
        icon: ShoppingBag,
    },
    {
        title: 'Stock y movimientos',
        description: 'Alertas inteligentes, recetas y ajustes masivos para no perder insumos.',
        icon: Boxes,
    },
    {
        title: 'Reportes en tiempo real',
        description: 'Dashboards con KPIs diarios, históricos y proyecciones en segundos.',
        icon: BarChart3,
    },
    {
        title: 'Multi-tenant / multi-negocio',
        description: 'Administra varias marcas o sucursales desde una sola sesión segura.',
        icon: Layers,
    },
    {
        title: 'Roles y permisos',
        description: 'Define accesos granulares para cajas, cocina, gerencia y franquicias.',
        icon: ShieldCheck,
    },
    {
        title: 'Menú QR para restaurantes',
        description: 'Publica menús digitales sincronizados con precios y disponibilidad.',
        icon: QrCode,
    },
];

export const INDUSTRIES: IndustryItem[] = [
    {
        id: 'restaurantes',
        label: 'Restaurantes',
        description: 'Controla salones, delivery y cocina con tickets vivos y comandas claras.',
        bullets: ['Seguimiento por mesa y mozo', 'Comandas digitales para cocina/bar', 'Integraciones con apps de delivery'],
        highlight: 'Pensado para cadenas gastronómicas y dark kitchens.',
    },
    {
        id: 'comercios',
        label: 'Comercios',
        description: 'Sincroniza sucursales físicas y ventas online con stock centralizado.',
        bullets: ['Catálogos y combos ilimitados', 'Usuarios ilimitados por turno', 'Visibilidad de márgenes y promociones'],
        highlight: 'Ideal para retail, minimercados y franquicias.',
    },
    {
        id: 'servicios',
        label: 'Servicios',
        description: 'Administra agendas, pagos recurrentes y equipos móviles en campo.',
        bullets: ['Órdenes de trabajo compartidas', 'Alertas automáticas de cobro', 'Reportes por cliente o contrato'],
        highlight: 'Perfecto para catering, mantenimiento y consultorías.',
    },
];

export const HOW_IT_WORKS_STEPS = [
    {
        title: 'Creás tu negocio',
        description: 'Configura marca, canales y roles con un onboarding guiado.',
    },
    {
        title: 'Cargás productos',
        description: 'Importa menús o catálogos con plantillas CSV y presets por rubro.',
    },
    {
        title: 'Vendés y medís',
        description: 'Activa cajas, cobra y analiza métricas al instante.',
    },
];

export const PLANS: PlanItem[] = [
    {
        name: 'Starter',
        tagline: 'Desde tu primer punto de venta',
        priceNote: 'Desde $ por negocio / mes',
        bullets: ['POS ilimitado', 'Soporte base', 'Reportes esenciales'],
        ctaLabel: 'Ver precios',
    },
    {
        name: 'Pro',
        tagline: 'Escala equipos y sucursales',
        priceNote: 'Desde $ para equipos en crecimiento',
        bullets: ['Roles avanzados', 'Automatizaciones', 'Integraciones externas'],
        ctaLabel: 'Ver precios',
    },
    {
        name: 'Enterprise',
        tagline: 'Operaciones reguladas o franquicias',
        priceNote: 'A medida según operación',
        bullets: ['SLA dedicado', 'Onboarding asistido', 'Integraciones personalizadas'],
        ctaLabel: 'Ver precios',
    },
];
