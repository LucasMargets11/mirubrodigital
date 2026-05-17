"use client";

import { useState, useMemo, useTransition, useRef, useEffect } from 'react';
import Link from 'next/link';
import type { Route } from 'next';
import { usePathname } from 'next/navigation';
import { ChevronDown, ChevronRight, LogOut } from 'lucide-react';

import { cn } from '@/lib/utils';
import { logout } from '@/lib/auth/client';
import { serviceDisplayName, planDisplayName } from '@/lib/services';
import type { FeatureFlags, PermissionMap } from '@/lib/auth/types';

type AppLink = {
    href?: string;
    label: string;
    featureKey?: keyof FeatureFlags;
    permissionKey?: string;
    roleKey?: string;
    planKey?: string;
    services?: string[];
    children?: AppLink[];
};

type NavGroup = {
    title: string;
    items: AppLink[];
};

const NAV_CONFIG: Record<string, NavGroup[]> = {
    restaurante: [
        {
            title: 'Panel',
            items: [
                { href: '/app/dashboard', label: 'Inicio' },
                { href: '/app/owner', label: 'Sucursales', permissionKey: 'manage_settings', featureKey: 'multi_branch' },
                { href: '/app/servicios', label: 'Servicios' },
            ],
        },
        {
            title: 'Restaurante Inteligente',
            items: [
                { href: '/app/tables', label: 'Mapa de mesas', permissionKey: 'view_tables', featureKey: 'resto_tables' },
                { href: '/app/orders', label: 'Órdenes', permissionKey: 'view_orders', featureKey: 'resto_orders' },
                { href: '/app/kitchen', label: 'Cocina en vivo', permissionKey: 'view_kitchen_board', featureKey: 'resto_kitchen' },
                { href: '/app/carta', label: 'Carta', permissionKey: 'view_menu', featureKey: 'resto_menu' },
            ],
        },
        {
            title: 'Gestión Comercial',
            items: [
                { href: '/app/gestion/dashboard', label: 'Resumen', permissionKey: 'view_dashboard' },
                { href: '/app/gestion/productos', label: 'Productos', permissionKey: 'view_products', featureKey: 'products' },
                { href: '/app/gestion/stock', label: 'Stock', permissionKey: 'view_stock', featureKey: 'inventory' },
                { href: '/app/gestion/ventas', label: 'Ventas', permissionKey: 'view_sales', featureKey: 'sales' },
                { href: '/app/gestion/facturas', label: 'Facturas', permissionKey: 'view_invoices', featureKey: 'invoices' },
                { href: '/app/gestion/clientes', label: 'Clientes', permissionKey: 'view_customers', featureKey: 'customers' },
                { href: '/app/gestion/carteles', label: 'Carteles y Etiquetas', featureKey: 'print_signage' },
            ],
        },
        {
            title: 'Operación',
            items: [
                { href: '/app/operacion/caja', label: 'Caja', permissionKey: 'view_cash', featureKey: 'cash' },
                {
                    href: '/app/resto/operacion/reportes',
                    label: 'Reportes',
                    permissionKey: 'view_restaurant_reports',
                    featureKey: 'resto_reports',
                },
                {
                    label: 'Configuración',
                    permissionKey: 'manage_settings',
                    featureKey: 'settings',
                    children: [
                        { href: '/app/settings', label: 'General' },
                        { href: '/app/settings/access', label: 'Roles & Accesos', permissionKey: 'manage_users' },
                        { href: '/app/settings/branches', label: 'Sucursales', permissionKey: 'manage_settings' }, // Access check in page
                        {
                            href: '/app/carta/apariencia',
                            label: 'Personalización (Carta)',
                            permissionKey: 'manage_settings',
                            featureKey: 'resto_menu',
                        },
                        {
                            href: '/app/resto/settings/tables',
                            label: 'Configurar mesas',
                            permissionKey: 'manage_tables',
                            featureKey: 'resto_tables',
                        },
                    ],
                },
                { href: '/app/soporte', label: 'Soporte', roleKey: 'owner' },
            ],
        },
    ],
    gestion: [
        {
            title: 'Panel',
            items: [
                { href: '/app/dashboard', label: 'Inicio' },
                { href: '/app/owner', label: 'Sucursales', permissionKey: 'manage_settings', featureKey: 'multi_branch' },
                { href: '/app/servicios', label: 'Servicios' },
            ],
        },
        {
            title: 'Gestión Comercial',
            items: [
                { href: '/app/gestion/dashboard', label: 'Resumen', permissionKey: 'view_dashboard' },
                { href: '/app/gestion/productos', label: 'Productos', permissionKey: 'view_products', featureKey: 'products' },
                { href: '/app/gestion/stock', label: 'Stock', permissionKey: 'view_stock', featureKey: 'inventory' },
                { href: '/app/gestion/ventas', label: 'Ventas', permissionKey: 'view_sales', featureKey: 'sales' },
                { href: '/app/gestion/ventas/pedidos', label: 'Pedidos', permissionKey: 'view_orders', featureKey: 'orders' },
                { href: '/app/gestion/ventas/presupuestos', label: 'Presupuestos', permissionKey: 'view_quotes', featureKey: 'quotes' },
                { href: '/app/gestion/facturas', label: 'Facturas', permissionKey: 'view_invoices', featureKey: 'invoices' },
                { href: '/app/gestion/finanzas', label: 'Finanzas', permissionKey: 'view_finance', featureKey: 'treasury' },
                { href: '/app/gestion/clientes', label: 'Clientes', permissionKey: 'view_customers', featureKey: 'customers' },
                { href: '/app/gestion/carteles', label: 'Carteles y Etiquetas', featureKey: 'print_signage' },
            ],
        },
        {
            title: 'Operación',
            items: [
                { href: '/app/operacion/caja', label: 'Caja', permissionKey: 'view_cash', featureKey: 'cash' },
                { href: '/app/gestion/reportes', label: 'Reportes', permissionKey: 'view_dashboard' },
                {
                    label: 'Configuración',
                    permissionKey: 'manage_commercial_settings',
                    featureKey: 'settings',
                    children: [
                        { href: '/app/gestion/configuracion', label: 'General' },
                        { href: '/app/gestion/configuracion/negocio', label: 'Negocio', permissionKey: 'manage_commercial_settings' },
                        { href: '/app/gestion/configuracion/plan-facturacion', label: 'Plan y Facturación' },
                    ],
                },
                {
                    href: '/app/settings/access',
                    label: 'Roles & Accesos',
                    permissionKey: 'manage_users',
                },
                { href: '/app/soporte', label: 'Soporte', roleKey: 'owner' },
            ],
        },
    ],
    menu_qr: [
        {
            title: 'Menú QR',
            items: [
                { href: '/app/carta', label: 'Contenido', permissionKey: 'view_menu' },
                { href: '/app/carta/estructura', label: 'Estructura', permissionKey: 'view_menu' },
                { href: '/app/carta/apariencia', label: 'Apariencia', permissionKey: 'manage_menu_branding' },
                { href: '/app/carta/publicacion', label: 'Publicación', permissionKey: 'view_menu_admin' },
                { href: '/app/carta/engagement', label: 'Engagement', permissionKey: 'view_menu' },
            ],
        },
        {
            title: 'Cuenta',
            items: [
                { href: '/app/servicios', label: 'Planes y upgrades' },
                { href: '/app/planes', label: 'Facturación' },
                { href: '/app/settings', label: 'Configuración' },
                { href: '/app/settings/access', label: 'Roles & Accesos', permissionKey: 'manage_users' },
                { href: '/app/soporte', label: 'Soporte', roleKey: 'owner' },
            ],
        },
    ],
    qr_reviews: [
        {
            title: 'QR de Reseñas',
            items: [
                { href: '/app/resenas', label: 'Inicio' },
                { href: '/app/resenas/qr', label: 'Mi QR', permissionKey: 'manage_reviews' },
                { href: '/app/resenas/carteles', label: 'Carteles', permissionKey: 'manage_reviews', planKey: 'qr_reviews_pro' },
                { href: '/app/resenas/feedback', label: 'Feedback', permissionKey: 'manage_reviews' },
                { href: '/app/resenas/analytics', label: 'Analytics', permissionKey: 'manage_reviews', planKey: 'qr_reviews_pro' },
            ],
        },
        {
            title: 'Administración',
            items: [
                { href: '/app/resenas/configuracion', label: 'Configuración', permissionKey: 'manage_reviews' },
                { href: '/app/settings/access', label: 'Roles y accesos', permissionKey: 'manage_users' },
                { href: '/app/planes', label: 'Plan y facturación' },
            ],
        },
        {
            title: '',
            items: [
                { href: '/app/soporte', label: 'Soporte' },
            ],
        },
    ],
};

type ScrollableNavProps = {
    children: React.ReactNode;
    className?: string;
};

function ScrollableNav({ children, className }: ScrollableNavProps) {
    const scrollRef = useRef<HTMLDivElement>(null);
    const [showTopFade, setShowTopFade] = useState(false);
    const [showBottomFade, setShowBottomFade] = useState(false);

    const checkScroll = () => {
        const element = scrollRef.current;
        if (!element) return;

        const { scrollTop, scrollHeight, clientHeight } = element;
        const isScrollable = scrollHeight > clientHeight;

        // Show top fade if scrolled down
        setShowTopFade(isScrollable && scrollTop > 10);

        // Show bottom fade if not at bottom
        setShowBottomFade(isScrollable && scrollTop + clientHeight < scrollHeight - 10);
    };

    useEffect(() => {
        checkScroll();
        const element = scrollRef.current;
        if (!element) return;

        const resizeObserver = new ResizeObserver(checkScroll);
        resizeObserver.observe(element);

        return () => resizeObserver.disconnect();
    }, [children]);

    return (
        <div className="relative flex-1 min-h-0">
            {/* Top fade indicator */}
            <div
                className={cn(
                    'absolute left-0 right-0 top-0 z-10 h-8 pointer-events-none transition-opacity duration-300',
                    'bg-gradient-to-b from-white to-transparent',
                    showTopFade ? 'opacity-100' : 'opacity-0'
                )}
            />

            {/* Scrollable content */}
            <div
                ref={scrollRef}
                onScroll={checkScroll}
                className={cn('sidebar-scroll h-full overflow-y-auto', className)}
            >
                {children}
            </div>

            {/* Bottom fade indicator */}
            <div
                className={cn(
                    'absolute left-0 right-0 bottom-0 z-10 h-8 pointer-events-none transition-opacity duration-300',
                    'bg-gradient-to-t from-white to-transparent',
                    showBottomFade ? 'opacity-100' : 'opacity-0'
                )}
            />
        </div>
    );
}

type SidebarProps = {
    businessName: string;
    branchName?: string;
    features: FeatureFlags;
    permissions: PermissionMap;
    service: string;
    userName: string;
    role: string;
    subscriptionStatus: string;
    subscriptionPlan?: string;
    isMobile?: boolean;
    onNavigate?: () => void;
};

type AccountHeaderProps = {
    businessName: string;
    branchName?: string;
    userName: string;
    role: string;
    subscriptionPlan?: string;
    subscriptionStatus: string;
    service: string;
};

function AccountHeader({ 
    businessName, 
    branchName, 
    userName, 
    role, 
    subscriptionPlan,
    subscriptionStatus,
    service 
}: AccountHeaderProps) {
    const [error, setError] = useState<string | null>(null);
    const [isPending, startTransition] = useTransition();

    const initials = useMemo(() => {
        if (!userName) {
            return '??';
        }
        return userName
            .split(' ')
            .filter(Boolean)
            .map((part) => part[0]?.toUpperCase())
            .slice(0, 2)
            .join('');
    }, [userName]);

    const handleLogout = () => {
        setError(null);
        startTransition(async () => {
            try {
                await logout();
            } catch (err) {
                setError('Error al cerrar sesión.');
            }
        });
    };

    const serviceLabel = serviceDisplayName(service);
    const displayRole = role === 'owner' ? 'Dueño' : role === 'manager' ? 'Gerente' : 'Staff';
    const hasIssue = subscriptionStatus !== 'active';

    return (
        <div className="border-b border-slate-200 px-4 py-4 space-y-3">
            {/* Business Info */}
            <div className="space-y-1">
                <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-slate-900 truncate">
                            {businessName}
                        </p>
                        {branchName && (
                            <p className="text-xs text-slate-500 truncate">
                                {branchName}
                            </p>
                        )}
                    </div>
                    {subscriptionPlan && (
                        <span className="shrink-0 rounded-full bg-brand-100 px-2 py-0.5 text-xs font-medium text-brand-700">
                            {planDisplayName(subscriptionPlan)}
                        </span>
                    )}
                </div>
                <p className="text-xs text-slate-500">
                    {displayRole} · {serviceLabel}
                </p>
            </div>

            {/* User Info & Actions */}
            <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-700">
                    {initials}
                </div>
                <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 truncate">
                        {userName}
                    </p>
                </div>
                <button
                    type="button"
                    onClick={handleLogout}
                    disabled={isPending}
                    className="shrink-0 rounded-md p-2 text-slate-600 hover:bg-slate-100 hover:text-slate-900 disabled:opacity-60 transition-colors"
                    aria-label="Cerrar sesión"
                    title="Salir"
                >
                    <LogOut className="h-4 w-4" />
                </button>
            </div>

            {/* Status Warning (only if there's an issue) */}
            {hasIssue && (
                <div className="rounded-md bg-amber-50 border border-amber-200 px-3 py-2">
                    <p className="text-xs text-amber-800">
                        Estado: <span className="font-medium">{subscriptionStatus}</span>
                    </p>
                    <Link 
                        href="/app/planes"
                        className="text-xs text-amber-900 underline hover:no-underline"
                    >
                        Revisar facturación
                    </Link>
                </div>
            )}

            {error && (
                <p className="text-xs text-red-600">{error}</p>
            )}
        </div>
    );
}

function NavItem({ item, pathname, onNavigate }: { item: AppLink; pathname: string; onNavigate?: () => void }) {
    const isActive = item.href ? pathname?.startsWith(item.href) : false;
    // Check if any child is active to auto-expand or highlight parent
    const hasActiveChild = item.children?.some((child) => child.href && pathname?.startsWith(child.href));

    // Initialize open state if a child is active
    const [isOpen, setIsOpen] = useState(hasActiveChild);

    if (item.children) {
        return (
            <div className="space-y-0.5">
                <button
                    onClick={() => setIsOpen(!isOpen)}
                    aria-expanded={isOpen}
                    className={cn(
                        'flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-sm transition-colors',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1',
                        hasActiveChild
                            ? 'bg-brand-50 text-brand-900 font-semibold'
                            : 'text-slate-600 font-medium hover:bg-slate-50 hover:text-slate-800'
                    )}
                >
                    <span>{item.label}</span>
                    {isOpen ? <ChevronDown className="h-4 w-4" aria-hidden="true" /> : <ChevronRight className="h-4 w-4" aria-hidden="true" />}
                </button>
                {isOpen && (
                    <div className="ml-3 space-y-0.5 border-l border-slate-200 pl-2">
                        {item.children.map((child) => (
                            <NavItem key={child.href || child.label} item={child} pathname={pathname} onNavigate={onNavigate} />
                        ))}
                    </div>
                )}
            </div>
        );
    }

    if (!item.href) return null;

    return (
        <Link
            href={item.href as Route}
            onClick={() => onNavigate?.()}
            aria-current={isActive ? 'page' : undefined}
            className={cn(
                'block rounded-lg px-3 py-2.5 text-sm transition-all duration-150',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1',
                isActive
                    ? 'bg-brand-600 text-white font-semibold shadow-sm'
                    : 'text-slate-600 font-medium hover:bg-slate-100 hover:text-slate-900'
            )}
        >
            {item.label}
        </Link>
    );
}

export function Sidebar({ 
    businessName, 
    branchName,
    features, 
    permissions, 
    service, 
    userName,
    role,
    subscriptionStatus,
    subscriptionPlan,
    isMobile, 
    onNavigate 
}: SidebarProps) {
    const pathname = usePathname() || '';

    // Fallback to empty list or default structure if service not found, 
    // but here we just handle the known ones or fallback to 'gestion' structure if needed.
    // For now assuming service is valid as per previous code.
    const sections = NAV_CONFIG[service] ?? [];

    return (
        <aside
            aria-label="Navegación principal"
            className={cn(
                "flex w-full flex-col bg-white",
                isMobile ? "h-full" : "sticky top-0 h-screen w-64 border-r border-slate-200"
            )}
        >
            <AccountHeader 
                businessName={businessName}
                branchName={branchName}
                userName={userName}
                role={role}
                subscriptionPlan={subscriptionPlan}
                subscriptionStatus={subscriptionStatus}
                service={service}
            />
            <ScrollableNav className="space-y-5 px-3 py-4 text-sm">
                {sections.map((section) => {
                    const visibleLinks = section.items.filter((link) => {
                        if (link.services && !link.services.includes(service)) {
                            return false;
                        }
                        if (link.featureKey && features?.[link.featureKey] === false) {
                            return false;
                        }
                        if (link.permissionKey && permissions?.[link.permissionKey] !== true) {
                            return false;
                        }
                        if (link.roleKey && link.roleKey !== role) {
                            return false;
                        }
                        if (link.planKey && subscriptionPlan !== link.planKey) {
                            return false;
                        }
                        return true;
                    });

                    if (visibleLinks.length === 0) return null;

                    return (
                        <div key={section.title || '_secondary'} className="space-y-1.5">
                            {section.title && <p className="px-3 pb-1 text-[11px] font-bold uppercase tracking-wider text-slate-400/90">{section.title}</p>}
                            {visibleLinks.map((link) => (
                                <NavItem key={link.href || link.label} item={link} pathname={pathname} onNavigate={onNavigate} />
                            ))}
                        </div>
                    );
                })}
            </ScrollableNav>
        </aside>
    );
}
