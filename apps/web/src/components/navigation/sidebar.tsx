"use client";

import { useState, useMemo, useTransition } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronDown, ChevronRight, LogOut } from 'lucide-react';

import { cn } from '@/lib/utils';
import { logout } from '@/lib/auth/client';
import type { FeatureFlags, PermissionMap } from '@/lib/auth/types';

const SERVICE_LABELS: Record<string, string> = {
    gestion: 'Gestión Comercial',
    restaurante: 'Restaurante Inteligente',
    menu_qr: 'Menú QR Online',
};

type AppLink = {
    href?: string;
    label: string;
    featureKey?: keyof FeatureFlags;
    permissionKey?: string;
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
                            href: '/app/settings/online-menu',
                            label: 'Carta Online',
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
                { href: '/app/gestion/facturas', label: 'Facturas', permissionKey: 'view_invoices', featureKey: 'invoices' },
                { href: '/app/gestion/finanzas', label: 'Finanzas', permissionKey: 'view_finance', featureKey: 'treasury' },
                { href: '/app/gestion/clientes', label: 'Clientes', permissionKey: 'view_customers', featureKey: 'customers' },
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
                    ],
                },
                {
                    href: '/app/settings/access',
                    label: 'Roles & Accesos',
                    permissionKey: 'manage_users',
                },
            ],
        },
    ],
    menu_qr: [
        {
            title: 'Menú QR',
            items: [
                { href: '/app/menu', label: 'Carta Online', permissionKey: 'view_menu' },
                { href: '/app/menu/branding', label: 'Branding', permissionKey: 'manage_menu_branding' },
                { href: '/app/menu/qr', label: 'QR y enlaces', permissionKey: 'view_menu_admin' },
                { href: '/app/menu/preview', label: 'Preview público', permissionKey: 'view_menu' },
            ],
        },
        {
            title: 'Cuenta',
            items: [
                { href: '/app/servicios', label: 'Planes y upgrades' },
                { href: '/app/planes', label: 'Facturación' },
                { href: '/app/settings', label: 'Configuración' },
                { href: '/app/settings/access', label: 'Roles & Accesos', permissionKey: 'manage_users' },
            ],
        },
    ],
};

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

    const serviceLabel = SERVICE_LABELS[service] ?? service;
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
                            {subscriptionPlan}
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
            <div className="space-y-1">
                <button
                    onClick={() => setIsOpen(!isOpen)}
                    className={cn(
                        'flex w-full items-center justify-between rounded-md px-3 py-2 text-left font-medium text-slate-600 hover:bg-brand-50',
                        hasActiveChild && 'bg-brand-50 text-brand-700'
                    )}
                >
                    <span>{item.label}</span>
                    {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                </button>
                {isOpen && (
                    <div className="ml-4 space-y-1 border-l border-slate-200 pl-2">
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
            href={item.href}
            onClick={() => onNavigate?.()}
            className={cn(
                'block rounded-md px-3 py-2 font-medium text-slate-600 hover:bg-brand-50',
                isActive && 'bg-brand-100 text-brand-700'
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
        <aside className={cn(
            "flex w-full flex-col bg-white",
            isMobile ? "h-full" : "sticky top-0 h-screen w-64 border-r border-slate-200"
        )}>
            <AccountHeader 
                businessName={businessName}
                branchName={branchName}
                userName={userName}
                role={role}
                subscriptionPlan={subscriptionPlan}
                subscriptionStatus={subscriptionStatus}
                service={service}
            />
            <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4 text-sm">
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
                        return true;
                    });

                    if (visibleLinks.length === 0) return null;

                    return (
                        <div key={section.title} className="space-y-1">
                            <p className="px-3 text-xs font-semibold uppercase tracking-wide text-slate-400">{section.title}</p>
                            {visibleLinks.map((link) => (
                                <NavItem key={link.href || link.label} item={link} pathname={pathname} onNavigate={onNavigate} />
                            ))}
                        </div>
                    );
                })}
            </nav>
        </aside>
    );
}
