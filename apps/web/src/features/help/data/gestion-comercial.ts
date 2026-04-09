import type {
    GestionPlan,
    HowToItem,
    SetupSection,
    SetupStep,
    TipItem,
    UpgradeNudge,
} from '../types';

// ─── Sections ─────────────────────────────────────────────────────────

export const GESTION_SECTIONS: SetupSection[] = [
    { key: 'tu-negocio', label: 'Tu negocio', minPlan: 'start' },
    { key: 'tu-catalogo', label: 'Tu catálogo', minPlan: 'start' },
    { key: 'tu-inventario', label: 'Tu inventario', minPlan: 'start' },
    { key: 'tus-finanzas', label: 'Tus finanzas', minPlan: 'pro' },
    { key: 'facturacion', label: 'Facturación', minPlan: 'pro' },
    { key: 'tu-equipo', label: 'Tu equipo', minPlan: 'pro' },
    { key: 'tu-estructura', label: 'Tu estructura', minPlan: 'business' },
];

// ─── Setup steps (V2.1) ──────────────────────────────────────────────

export const GESTION_SETUP_STEPS: SetupStep[] = [
    {
        id: 'gestion.business_and_fiscal',
        title: 'Completar los datos de tu negocio',
        description: 'Nombre, dirección, CUIT y condición ante IVA. Todo en un solo lugar.',
        section: 'tu-negocio',
        minPlan: 'start',
        obligation: 'required',
        cta: { label: 'Completar datos', href: '/app/gestion/configuracion/negocio' },
    },
    {
        id: 'gestion.branding',
        title: 'Subir tu logo para facturas y presupuestos',
        description: 'El logo aparece en el encabezado de tus documentos comerciales en PDF.',
        section: 'tu-negocio',
        minPlan: 'start',
        obligation: 'recommended',
        cta: { label: 'Subir logo', href: '/app/gestion/configuracion/negocio' },
    },
    {
        id: 'gestion.categories',
        title: 'Crear categorías de productos',
        description: 'Organizá tu catálogo por rubros o familias antes de cargar productos.',
        section: 'tu-catalogo',
        minPlan: 'start',
        obligation: 'recommended',
        cta: { label: 'Crear categoría', href: '/app/gestion/productos/categorias' },
    },
    {
        id: 'gestion.products',
        title: 'Cargar tu catálogo de productos',
        description:
            'La base de ventas, stock y facturación. Podés importar un Excel o crear uno por uno.',
        section: 'tu-catalogo',
        minPlan: 'start',
        obligation: 'required',
        cta: { label: 'Importar Excel', href: '/app/gestion/stock/importar' },
        ctaSecondary: { label: 'Crear manualmente', href: '/app/gestion/productos' },
        hint: '¿Tenés muchos productos? La importación Excel te permite cargar hasta 2000 de una vez.',
    },
    {
        id: 'gestion.initial_stock',
        title: 'Definir el stock inicial',
        description:
            'Cargá las cantidades actuales de cada producto para activar alertas y control de inventario.',
        section: 'tu-inventario',
        minPlan: 'start',
        obligation: 'recommended',
        cta: { label: 'Cargar stock', href: '/app/gestion/stock' },
    },
    {
        id: 'gestion.treasury_accounts',
        title: 'Crear tus cuentas de dinero',
        description:
            'Definí dónde entra y sale la plata: efectivo, banco, Mercado Pago.',
        section: 'tus-finanzas',
        minPlan: 'pro',
        obligation: 'required',
        cta: { label: 'Crear cuenta', href: '/app/gestion/finanzas/cuentas' },
    },
    {
        id: 'gestion.cash_link',
        title: 'Vincular caja con cuenta de efectivo',
        description:
            'Asigná la cuenta de efectivo como destino de los cobros en caja.',
        section: 'tus-finanzas',
        minPlan: 'pro',
        obligation: 'recommended',
        cta: { label: 'Configurar', href: '/app/gestion/finanzas/configuracion' },
    },
    {
        id: 'gestion.document_series',
        title: 'Crear series de documentos',
        description:
            'Definí punto de venta, tipo de letra (A/B/C) y numeración para tus comprobantes.',
        section: 'facturacion',
        minPlan: 'pro',
        obligation: 'recommended',
        cta: { label: 'Crear serie', href: '/app/gestion/configuracion/negocio' },
    },
    {
        id: 'gestion.team',
        title: 'Invitar a tu equipo',
        description:
            'Agregá empleados y asigná roles para que cada uno acceda solo a lo que necesita.',
        section: 'tu-equipo',
        minPlan: 'pro',
        obligation: 'optional',
        cta: { label: 'Invitar', href: '/app/settings/access' },
    },
    {
        id: 'gestion.branches',
        title: 'Crear sucursales',
        description:
            'Creá sucursales para manejar reportes consolidados y transferencias entre locales.',
        section: 'tu-estructura',
        minPlan: 'business',
        obligation: 'recommended',
        cta: { label: 'Crear sucursal', href: '/app/owner' },
    },
];

// ─── How-to items ─────────────────────────────────────────────────────

export const GESTION_HOWTO_ITEMS: HowToItem[] = [
    {
        id: 'howto.sale',
        title: 'Registrar una venta',
        description: 'Cargá ventas desde el panel con productos, cantidad y método de pago.',
        href: '/app/gestion/ventas',
        minPlan: 'start',
    },
    {
        id: 'howto.cash',
        title: 'Cobrar desde la caja',
        description: 'Abrí una sesión de caja, cobrá ventas y cerrá el turno con arqueo.',
        href: '/app/operacion/caja',
        minPlan: 'pro',
    },
    {
        id: 'howto.customer',
        title: 'Cargar un cliente',
        description: 'Creá clientes para asociar ventas y llevar historial de compras.',
        href: '/app/gestion/clientes',
        minPlan: 'pro',
    },
    {
        id: 'howto.invoice',
        title: 'Emitir una factura',
        description: 'Generá facturas vinculadas a ventas con tu perfil fiscal configurado.',
        href: '/app/gestion/facturas',
        minPlan: 'pro',
    },
    {
        id: 'howto.expense',
        title: 'Registrar un gasto',
        description: 'Cargá gastos puntuales o fijos y vinculalos a cuentas de dinero.',
        href: '/app/gestion/finanzas/gastos',
        minPlan: 'pro',
    },
    {
        id: 'howto.stock_movement',
        title: 'Hacer un movimiento de stock',
        description: 'Registrá entradas, salidas, ajustes o mermas en tu inventario.',
        href: '/app/gestion/stock',
        minPlan: 'start',
    },
    {
        id: 'howto.replenishment',
        title: 'Registrar una compra / reposición',
        description: 'Cargá compras a proveedores que ajusten stock y generen gasto automático.',
        href: '/app/gestion/stock',
        minPlan: 'pro',
    },
    {
        id: 'howto.reports',
        title: 'Consultar reportes',
        description: 'Revisá métricas de ventas, stock y finanzas desde el panel de reportes.',
        href: '/app/gestion/reportes',
        minPlan: 'pro',
    },
];

// ─── Tips ─────────────────────────────────────────────────────────────

export const GESTION_TIPS: TipItem[] = [
    {
        id: 'tip.categories',
        text: 'Usá categorías para organizar tu catálogo y encontrar productos más rápido.',
        minPlan: 'start',
    },
    {
        id: 'tip.stock_alerts',
        text: 'Configurá alertas de stock bajo para no quedarte sin mercadería.',
        minPlan: 'start',
    },
    {
        id: 'tip.stock_min',
        text: 'Definí un stock mínimo por producto para que las alertas sean precisas.',
        minPlan: 'start',
    },
    {
        id: 'tip.customer_history',
        text: 'Asociá ventas a clientes para tener historial y poder fidelizar.',
        minPlan: 'pro',
        ctaLabel: 'Ver planes →',
        ctaHref: '/app/settings/billing',
    },
    {
        id: 'tip.csv_export',
        text: 'Exportá reportes en CSV para compartir con tu contador.',
        minPlan: 'pro',
        ctaLabel: 'Ver planes →',
        ctaHref: '/app/settings/billing',
    },
    {
        id: 'tip.quotes',
        text: 'Usá presupuestos para enviar cotizaciones antes de cerrar la venta.',
        minPlan: 'pro',
        ctaLabel: 'Ver planes →',
        ctaHref: '/app/settings/billing',
    },
    {
        id: 'tip.fixed_expenses',
        text: 'Configurá gastos fijos (alquiler, servicios) para automatizar seguimiento mensual.',
        minPlan: 'pro',
    },
    {
        id: 'tip.reconciliation',
        text: 'Reconciliá tus cuentas periódicamente para detectar diferencias.',
        minPlan: 'pro',
    },
    {
        id: 'tip.branches',
        text: 'Abrí sucursales para gestionar múltiples locales desde un panel.',
        minPlan: 'business',
        ctaLabel: 'Ver planes →',
        ctaHref: '/app/settings/billing',
    },
    {
        id: 'tip.tax_backup',
        text: 'Activá respaldo impositivo para digitalizar facturas recibidas con OCR.',
        minPlan: 'business',
        ctaLabel: 'Ver planes →',
        ctaHref: '/app/settings/billing',
    },
    {
        id: 'tip.consolidated',
        text: 'Consultá reportes consolidados para ver el rendimiento de todas tus sucursales.',
        minPlan: 'business',
        ctaLabel: 'Ver planes →',
        ctaHref: '/app/settings/billing',
    },
];

// ─── Upgrade nudges ───────────────────────────────────────────────────

export const GESTION_UPGRADE_NUDGES: Record<string, UpgradeNudge> = {
    start: {
        targetPlan: 'PRO',
        headline: '¿Necesitás más?',
        body: 'Con el plan PRO podés gestionar finanzas, emitir facturas y controlar accesos de tu equipo.',
        ctaLabel: 'Ver planes',
        ctaHref: '/app/settings/billing',
    },
    pro: {
        targetPlan: 'BUSINESS',
        headline: '¿Necesitás más?',
        body: 'Con BUSINESS podés crear sucursales, consolidar reportes y generar respaldos impositivos.',
        ctaLabel: 'Ver planes',
        ctaHref: '/app/settings/billing',
    },
};
