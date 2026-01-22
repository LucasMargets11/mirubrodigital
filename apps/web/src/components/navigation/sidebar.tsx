"use client";

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { cn } from '@/lib/utils';
import type { FeatureFlags, PermissionMap } from '@/lib/auth/types';

const SERVICE_LABELS: Record<string, string> = {
    gestion: 'Gestión Comercial',
    restaurante: 'Restaurante Inteligente',
};

type AppLink = {
    href: string;
    label: string;
    featureKey?: keyof FeatureFlags;
    permissionKey?: string;
};

const GENERAL_LINKS: AppLink[] = [
    { href: '/app/dashboard', label: 'Inicio' },
    { href: '/app/servicios', label: 'Servicios' },
];

const SERVICE_LINKS: Record<string, AppLink[]> = {
    gestion: [
        { href: '/app/gestion/dashboard', label: 'Resumen', permissionKey: 'view_dashboard' },
        { href: '/app/gestion/productos', label: 'Productos', permissionKey: 'view_products', featureKey: 'products' },
        { href: '/app/gestion/stock', label: 'Stock', permissionKey: 'view_stock', featureKey: 'inventory' },
        { href: '/app/gestion/ventas', label: 'Ventas', permissionKey: 'view_sales', featureKey: 'sales' },
        { href: '/app/gestion/facturas', label: 'Facturas', permissionKey: 'view_invoices', featureKey: 'invoices' },
        { href: '/app/gestion/clientes', label: 'Clientes', permissionKey: 'view_customers', featureKey: 'customers' },
    ],
    restaurante: [
        { href: '/app/orders', label: 'Órdenes', permissionKey: 'view_orders', featureKey: 'orders' },
        { href: '/app/sales', label: 'Ventas', permissionKey: 'view_sales', featureKey: 'sales' },
    ],
};

const SHARED_LINKS: AppLink[] = [
    { href: '/app/operacion/caja', label: 'Caja', permissionKey: 'view_cash', featureKey: 'cash' },
    { href: '/app/reports', label: 'Reportes', permissionKey: 'view_reports', featureKey: 'reports' },
    { href: '/app/settings', label: 'Configuración', permissionKey: 'manage_settings', featureKey: 'settings' },
];

type SidebarProps = {
    businessName: string;
    features: FeatureFlags;
    permissions: PermissionMap;
    service: string;
};

export function Sidebar({ businessName, features, permissions, service }: SidebarProps) {
    const pathname = usePathname();
    const serviceLabel = SERVICE_LABELS[service] ?? service;

    const sections = [
        { title: 'Panel', links: GENERAL_LINKS },
        { title: serviceLabel, links: SERVICE_LINKS[service] ?? [] },
        { title: 'Operación', links: SHARED_LINKS },
    ];

    return (
        <aside className="sticky top-0 flex h-screen w-64 flex-col border-r border-slate-200 bg-white/70 backdrop-blur">
            <div className="px-6 py-5">
                <p className="text-xs uppercase tracking-wide text-slate-400">Operando</p>
                <p className="text-lg font-display font-semibold text-brand-600">{businessName}</p>
                <p className="text-xs text-slate-400">Servicio: {serviceLabel}</p>
            </div>
            <nav className="flex-1 space-y-5 overflow-y-auto px-3 pb-4 text-sm">
                {sections.map((section) => {
                    const visibleLinks = section.links.filter((link) => {
                        if (link.featureKey && features?.[link.featureKey] === false) {
                            return false;
                        }
                        if (link.permissionKey && permissions?.[link.permissionKey] !== true) {
                            return false;
                        }
                        return true;
                    });

                    if (visibleLinks.length === 0) {
                        return null;
                    }

                    return (
                        <div key={section.title} className="space-y-1">
                            <p className="px-3 text-xs font-semibold uppercase tracking-wide text-slate-400">{section.title}</p>
                            {visibleLinks.map((link) => (
                                <Link
                                    key={link.href}
                                    href={link.href}
                                    className={cn(
                                        'block rounded-md px-3 py-2 font-medium text-slate-600 hover:bg-brand-50',
                                        pathname?.startsWith(link.href) && 'bg-brand-100 text-brand-700'
                                    )}
                                >
                                    {link.label}
                                </Link>
                            ))}
                        </div>
                    );
                })}
            </nav>
        </aside>
    );
}
