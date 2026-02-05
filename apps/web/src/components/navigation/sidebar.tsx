"use client";

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronDown, ChevronRight } from 'lucide-react';

import { cn } from '@/lib/utils';
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
                { href: '/app/owner', label: 'Sucursales', permissionKey: 'manage_settings' },
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
                { href: '/app/owner', label: 'Sucursales', permissionKey: 'manage_settings' },
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
                { href: '/app/gestion/finanzas', label: 'Finanzas', permissionKey: 'view_finance' },
                { href: '/app/gestion/clientes', label: 'Clientes', permissionKey: 'view_customers', featureKey: 'customers' },
            ],
        },
        {
            title: 'Operación',
            items: [
                { href: '/app/operacion/caja', label: 'Caja', permissionKey: 'view_cash', featureKey: 'cash' },
                { href: '/app/reports', label: 'Reportes', permissionKey: 'view_reports', featureKey: 'reports' },
                {
                    href: '/app/gestion/configuracion',
                    label: 'Configuración',
                    permissionKey: 'manage_commercial_settings',
                    featureKey: 'settings',
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
                { href: '/app/settings', label: 'Equipo', permissionKey: 'manage_users' },
            ],
        },
    ],
};

type SidebarProps = {
    businessName: string;
    features: FeatureFlags;
    permissions: PermissionMap;
    service: string;
};

function NavItem({ item, pathname }: { item: AppLink; pathname: string }) {
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
                            <NavItem key={child.href || child.label} item={child} pathname={pathname} />
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
            className={cn(
                'block rounded-md px-3 py-2 font-medium text-slate-600 hover:bg-brand-50',
                isActive && 'bg-brand-100 text-brand-700'
            )}
        >
            {item.label}
        </Link>
    );
}

export function Sidebar({ businessName, features, permissions, service }: SidebarProps) {
    const pathname = usePathname() || '';
    const serviceLabel = SERVICE_LABELS[service] ?? service;

    // Fallback to empty list or default structure if service not found, 
    // but here we just handle the known ones or fallback to 'gestion' structure if needed.
    // For now assuming service is valid as per previous code.
    const sections = NAV_CONFIG[service] ?? [];

    return (
        <aside className="sticky top-0 flex h-screen w-64 flex-col border-r border-slate-200 bg-white/70 backdrop-blur">
            <div className="px-6 py-5">
                <p className="text-xs uppercase tracking-wide text-slate-400">Operando</p>
                <p className="text-lg font-display font-semibold text-brand-600">{businessName}</p>
                <p className="text-xs text-slate-400">Servicio: {serviceLabel}</p>
            </div>
            <nav className="flex-1 space-y-5 overflow-y-auto px-3 pb-4 text-sm">
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
                                <NavItem key={link.href || link.label} item={link} pathname={pathname} />
                            ))}
                        </div>
                    );
                })}
            </nav>
        </aside>
    );
}
