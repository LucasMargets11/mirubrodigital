"use client";

import Link from 'next/link';

import { useCashSummary } from '@/features/cash/hooks';
import { useInventorySummary, usePendingQuotesSummary } from '@/features/gestion/hooks';
import type { DashboardFeatures, DashboardPermissions } from '../dashboard-client';
import { cn } from '@/lib/utils';

// ── Context ─────────────────────────────────────────────────────────
type DashboardCtx = {
    cashOpen: boolean;
    outOfStockCount: number;
    lowStockCount: number;
    pendingQuotesCount: number;
    hasProducts: boolean;
};

// ── Item types ───────────────────────────────────────────────────────
type IconProps = { className?: string };

type CatalogEntry = {
    key: string;
    /** Return label; ctx optional so string entries work too */
    label: (ctx: DashboardCtx) => string;
    description: (ctx: DashboardCtx) => string;
    href: (ctx: DashboardCtx) => string | undefined;
    intent: 'primary' | 'secondary' | 'ghost';
    icon: (props: IconProps) => JSX.Element;
    /** Return false to hide the action regardless of context */
    visible: (permissions: DashboardPermissions, features: DashboardFeatures) => boolean;
    /** Lower number = rendered first. May depend on context. */
    priority: (ctx: DashboardCtx) => number;
    tooltip?: string;
};

type ActionItem = {
    key: string;
    label: string;
    description: string;
    href?: string;
    intent: 'primary' | 'secondary' | 'ghost';
    icon: (props: IconProps) => JSX.Element;
    enabled: boolean;
    tooltip?: string;
};

type QuickActionsProps = {
    permissions: DashboardPermissions;
    features: DashboardFeatures;
};

// ── Catalog ──────────────────────────────────────────────────────────
const CATALOG: CatalogEntry[] = [
    {
        key: 'new-sale',
        label: () => 'Nueva venta',
        description: () => 'Ticket rápido para mostrador',
        href: () => '/app/gestion/ventas/nueva',
        intent: 'primary',
        icon: CartIcon,
        visible: (p, f) => p.canCreateSales && f.sales,
        priority: (ctx) => (ctx.cashOpen ? 5 : 15),
    },
    {
        key: 'open-cash',
        label: (ctx) => (ctx.cashOpen ? 'Ir a caja' : 'Abrir caja'),
        description: (ctx) =>
            ctx.cashOpen ? 'Caja activa · ver movimientos y cierres' : 'No hay sesión activa',
        href: () => '/app/operacion/caja',
        intent: 'secondary',
        icon: CashIcon,
        visible: (p, f) => p.canViewCash && f.cash,
        priority: (ctx) => (ctx.cashOpen ? 25 : 3),
    },
    {
        key: 'create-product',
        label: () => 'Crear producto',
        description: () => 'Alta con costos y precios',
        href: () => '/app/gestion/productos',
        intent: 'secondary',
        icon: PlusIcon,
        visible: (p, f) => p.canManageProducts && f.products,
        priority: (ctx) => (ctx.hasProducts ? 20 : 4),
    },
    {
        key: 'movement',
        label: () => 'Registrar movimiento',
        description: () => 'Entrada / salida / ajuste',
        href: () => '/app/gestion/stock?action=movement',
        intent: 'secondary',
        icon: ArrowsIcon,
        visible: (p, f) => p.canManageStock && f.inventory,
        priority: (ctx) =>
            ctx.outOfStockCount > 0 ? 6 : ctx.lowStockCount > 0 ? 10 : 30,
    },
    {
        key: 'view-out',
        label: () => 'Ver productos sin stock',
        description: () => 'Filtra productos con stock = 0',
        href: () => '/app/gestion/stock?status=out',
        intent: 'ghost',
        icon: AlertIcon,
        visible: (p, f) => p.canViewStock && f.inventory,
        priority: (ctx) => (ctx.outOfStockCount > 0 ? 7 : 70),
    },
    {
        key: 'view-quotes',
        label: () => 'Ver presupuestos',
        description: (ctx) =>
            ctx.pendingQuotesCount > 0
                ? `${ctx.pendingQuotesCount} pendientes de respuesta`
                : 'Listado de cotizaciones',
        href: () => '/app/gestion/ventas/presupuestos',
        intent: 'secondary',
        icon: ClipboardListIcon,
        visible: (p, f) => p.canViewQuotes && f.quotes,
        priority: (ctx) => (ctx.pendingQuotesCount > 0 ? 8 : 40),
    },
    {
        key: 'create-quote',
        label: () => 'Crear presupuesto',
        description: () => 'Nueva cotización para cliente',
        href: () => '/app/gestion/ventas/presupuestos/nuevo',
        intent: 'ghost',
        icon: FilePlusIcon,
        visible: (p, f) => p.canCreateQuotes && f.quotes,
        priority: (ctx) => (ctx.pendingQuotesCount > 0 ? 12 : 45),
    },
    {
        key: 'view-customers',
        label: () => 'Ver clientes',
        description: () => 'Historial y datos de clientes',
        href: () => '/app/gestion/clientes',
        intent: 'ghost',
        icon: UsersIcon,
        visible: (p, f) => p.canViewCustomers && f.customers,
        priority: () => 50,
    },
    {
        key: 'import',
        label: () => 'Importar stock (Excel)',
        description: () => 'Subí un .xlsx para crear y ajustar inventario',
        href: () => '/app/gestion/stock/importar',
        intent: 'ghost',
        icon: UploadIcon,
        visible: (p, f) => p.canManageStock && f.inventory,
        priority: (ctx) => (ctx.hasProducts ? 60 : 5),
    },
    {
        key: 'stock-min',
        label: () => 'Configurar stock mínimo',
        description: () => 'Definí alertas por producto',
        href: () => '/app/gestion/productos?focus=stock',
        intent: 'ghost',
        icon: ShieldIcon,
        visible: (p, f) => p.canManageProducts && f.inventory,
        priority: () => 75,
    },
    {
        key: 'view-invoices',
        label: () => 'Facturas',
        description: () => 'Emitir y gestionar comprobantes',
        href: () => '/app/gestion/facturas',
        intent: 'ghost',
        icon: ReceiptIcon,
        visible: (p, f) => p.canViewInvoices && f.invoices,
        priority: () => 80,
    },
    {
        key: 'view-finance',
        label: () => 'Finanzas',
        description: () => 'Cuentas y movimientos financieros',
        href: () => '/app/gestion/finanzas',
        intent: 'ghost',
        icon: WalletIcon,
        visible: (p, f) => p.canViewFinance && f.treasury,
        priority: () => 85,
    },
];

// ── Component ────────────────────────────────────────────────────────
export function QuickActions({ permissions, features }: QuickActionsProps) {
    // Re-uses cached React Query data populated by HealthCards — no extra requests
    const inventoryAllowed = permissions.canViewStock && features.inventory;
    const cashAllowed = permissions.canViewCash && features.cash;
    const quotesAllowed = permissions.canViewQuotes && features.quotes;

    const inventoryQuery = useInventorySummary({ enabled: inventoryAllowed });
    const cashQuery = useCashSummary(undefined, cashAllowed);
    const quotesQuery = usePendingQuotesSummary(quotesAllowed);

    const ctx: DashboardCtx = {
        cashOpen: Boolean(cashQuery.data?.session?.id),
        outOfStockCount: inventoryQuery.data?.out_of_stock ?? 0,
        lowStockCount: inventoryQuery.data?.low_stock ?? 0,
        pendingQuotesCount: quotesQuery.data?.count ?? 0,
        hasProducts: (inventoryQuery.data?.total_products ?? 0) > 0,
    };

    const actions: ActionItem[] = CATALOG.filter((entry) => entry.visible(permissions, features))
        .sort((a, b) => a.priority(ctx) - b.priority(ctx))
        .map((entry) => ({
            key: entry.key,
            label: entry.label(ctx),
            description: entry.description(ctx),
            href: entry.href(ctx),
            intent: entry.intent,
            icon: entry.icon,
            enabled: true,
            tooltip: entry.tooltip,
        }));

    if (actions.length === 0) return null;

    return (
        <section className="space-y-3">
            <div className="flex flex-col gap-1">
                <h2 className="text-lg font-semibold text-slate-900">Acciones rápidas</h2>
                <p className="text-sm text-slate-500">Atajos visuales para actuar sin salir del resumen.</p>
            </div>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                {actions.map((action) => (
                    <ActionCard key={action.key} action={action} />
                ))}
            </div>
        </section>
    );
}

function ActionCard({ action }: { action: ActionItem }) {
    const { label, description, href, intent, icon: Icon, tooltip } = action;
    const classes = cn(
        'relative flex flex-col gap-2 rounded-2xl border p-4 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900/20',
        intent === 'primary' && 'border-slate-900 bg-slate-900 text-white shadow-lg shadow-slate-900/10',
        intent === 'secondary' && 'border-slate-200 bg-white hover:border-slate-900 hover:text-slate-900',
        intent === 'ghost' && 'border-dashed border-slate-300 bg-slate-50 hover:border-slate-500'
    );

    const content = (
        <div className={classes} title={tooltip}>
            <div
                className={cn(
                    'inline-flex size-10 items-center justify-center rounded-2xl',
                    intent === 'primary' ? 'bg-white/20 text-white' : 'bg-white text-slate-900'
                )}
                aria-hidden="true"
            >
                <Icon className={cn('size-5', intent === 'primary' ? 'text-white' : 'text-slate-900')} />
            </div>
            <div>
                <p className="text-sm font-semibold">{label}</p>
                <p className={cn('text-xs', intent === 'primary' ? 'text-white/80' : 'text-slate-500')}>{description}</p>
            </div>
        </div>
    );

    if (href) {
        return (
            <Link href={href} className="block" aria-label={label}>
                {content}
            </Link>
        );
    }

    return content;
}

// ── Icons ────────────────────────────────────────────────────────────
function PlusIcon({ className }: IconProps) {
    return (
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6} className={className} aria-hidden="true">
            <path d="M10 4v12M4 10h12" strokeLinecap="round" />
        </svg>
    );
}

function ArrowsIcon({ className }: IconProps) {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className} aria-hidden="true">
            <path d="M7 7h10M7 17h10" strokeLinecap="round" />
            <path d="M14 4l3 3-3 3M10 20l-3-3 3-3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    );
}

function CartIcon({ className }: IconProps) {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className} aria-hidden="true">
            <circle cx="9" cy="20" r="1.5" />
            <circle cx="17" cy="20" r="1.5" />
            <path d="M5 5h2l1.2 8.4a2 2 0 0 0 2 1.6h6.9a2 2 0 0 0 2-1.6L20 8H9" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    );
}

function CashIcon({ className }: IconProps) {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className} aria-hidden="true">
            <rect x="2" y="7" width="20" height="14" rx="3" />
            <path d="M16 3H8C5.8 3 4 4.8 4 7" strokeLinecap="round" />
            <circle cx="12" cy="14" r="2.5" />
        </svg>
    );
}

function UploadIcon({ className }: IconProps) {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className} aria-hidden="true">
            <path d="M12 16V4" strokeLinecap="round" />
            <path d="M7 9l5-5 5 5" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M5 20h14" strokeLinecap="round" />
        </svg>
    );
}

function ShieldIcon({ className }: IconProps) {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className} aria-hidden="true">
            <path d="M12 3l8 3v6c0 4.5-3.1 8.6-8 9-4.9-.4-8-4.5-8-9V6l8-3z" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    );
}

function AlertIcon({ className }: IconProps) {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className} aria-hidden="true">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 7v5" strokeLinecap="round" />
            <circle cx="12" cy="16" r="0.5" fill="currentColor" stroke="none" />
        </svg>
    );
}

function FilePlusIcon({ className }: IconProps) {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className} aria-hidden="true">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M14 2v6h6" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M12 12v6M9 15h6" strokeLinecap="round" />
        </svg>
    );
}

function ClipboardListIcon({ className }: IconProps) {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className} aria-hidden="true">
            <path d="M9 5H7a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" strokeLinecap="round" strokeLinejoin="round" />
            <rect x="9" y="3" width="6" height="4" rx="1" />
            <path d="M9 12h6M9 16h4" strokeLinecap="round" />
        </svg>
    );
}

function UsersIcon({ className }: IconProps) {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className} aria-hidden="true">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx="9" cy="7" r="4" />
            <path d="M23 21v-2a4 4 0 0 0-3-3.87" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    );
}

function ReceiptIcon({ className }: IconProps) {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className} aria-hidden="true">
            <path d="M9 7h6M9 11h6M9 15h4" strokeLinecap="round" />
            <path d="M4 2v22l3-2 3 2 3-2 3 2 3-2V2l-3 2-3-2-3 2-3-2-3 2z" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    );
}

function WalletIcon({ className }: IconProps) {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className} aria-hidden="true">
            <path d="M20 12V8a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M20 12h-4a2 2 0 0 0 0 4h4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    );
}
