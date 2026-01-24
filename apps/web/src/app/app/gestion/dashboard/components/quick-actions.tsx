"use client";

import Link from 'next/link';

import type { DashboardFeatures, DashboardPermissions } from '../dashboard-client';
import { cn } from '@/lib/utils';

type QuickActionsProps = {
    permissions: DashboardPermissions;
    features: DashboardFeatures;
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

type IconProps = {
    className?: string;
};

export function QuickActions({ permissions, features }: QuickActionsProps) {
    const actions: ActionItem[] = [
        {
            key: 'create-product',
            label: 'Crear producto',
            description: 'Alta con costos y precios',
            href: '/app/gestion/productos',
            intent: 'primary',
            icon: PlusIcon,
            enabled: permissions.canManageProducts && features.products,
        },
        {
            key: 'movement',
            label: 'Registrar movimiento',
            description: 'Entrada / salida / ajuste',
            href: '/app/gestion/stock?action=movement',
            intent: 'secondary',
            icon: ArrowsIcon,
            enabled: permissions.canManageStock && features.inventory,
        },
        {
            key: 'new-sale',
            label: 'Nueva venta',
            description: features.sales ? 'Ticket rápido para mostrador' : 'Disponible pronto',
            href: features.sales ? '/app/gestion/ventas/nueva' : undefined,
            intent: 'secondary',
            icon: CartIcon,
            enabled: permissions.canCreateSales && features.sales,
            tooltip: features.sales ? undefined : 'Próximamente',
        },
        {
            key: 'open-cash',
            label: 'Ir a caja',
            description: features.cash ? 'Controlá movimientos y cierres diarios' : 'Disponible pronto',
            href: features.cash ? '/app/operacion/caja' : undefined,
            intent: 'secondary',
            icon: CashIcon,
            enabled: permissions.canViewCash && features.cash,
            tooltip: features.cash ? undefined : 'Próximamente',
        },
        {
            key: 'import',
            label: 'Importar stock (Excel)',
            description: 'Subí un .xlsx para crear y ajustar inventario',
            href: '/app/gestion/stock/importar',
            intent: 'ghost',
            icon: UploadIcon,
            enabled: permissions.canManageStock && features.inventory,
        },
        {
            key: 'stock-min',
            label: 'Configurar stock mínimo',
            description: 'Definí alertas por producto',
            href: '/app/gestion/productos?focus=stock',
            intent: 'ghost',
            icon: ShieldIcon,
            enabled: permissions.canManageProducts && features.inventory,
        },
        {
            key: 'view-out',
            label: 'Ver productos sin stock',
            description: 'Aplica filtros críticos',
            href: '/app/gestion/stock?status=out',
            intent: 'ghost',
            icon: AlertIcon,
            enabled: features.inventory && permissions.canViewStock,
        },
    ];

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
    const { label, description, href, intent, icon: Icon, enabled, tooltip } = action;
    const classes = cn(
        'relative flex flex-col gap-2 rounded-2xl border p-4 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900/20',
        intent === 'primary' && 'border-slate-900 bg-slate-900 text-white shadow-lg shadow-slate-900/10',
        intent === 'secondary' && 'border-slate-200 bg-white hover:border-slate-900 hover:text-slate-900',
        intent === 'ghost' && 'border-dashed border-slate-300 bg-slate-50 hover:border-slate-500',
        !enabled && 'cursor-not-allowed opacity-60'
    );

    const content = (
        <div className={classes} title={tooltip || (!enabled ? 'No disponible para tu rol actual' : undefined)} aria-disabled={!enabled}>
            <div
                className={cn(
                    'inline-flex size-10 items-center justify-center rounded-2xl',
                    intent === 'primary' ? 'bg-white/20 text-white' : 'bg-white text-slate-900'
                )}
            >
                <Icon className={cn('size-5', intent === 'primary' ? 'text-white' : 'text-slate-900')} />
            </div>
            <div>
                <p className="text-sm font-semibold">{label}</p>
                <p className={cn('text-xs', intent === 'primary' ? 'text-white/80' : 'text-slate-500')}>{description}</p>
            </div>
        </div>
    );

    if (href && enabled) {
        return (
            <Link href={href} className="block">
                {content}
            </Link>
        );
    }

    return content;
}

function PlusIcon({ className }: IconProps) {
    return (
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6} className={className}>
            <path d="M10 4v12M4 10h12" strokeLinecap="round" />
        </svg>
    );
}

function ArrowsIcon({ className }: IconProps) {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className}>
            <path d="M7 7h10M7 17h10" strokeLinecap="round" />
            <path d="M14 4l3 3-3 3M10 20l-3-3 3-3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    );
}

function CartIcon({ className }: IconProps) {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className}>
            <circle cx="9" cy="20" r="1.5" />
            <circle cx="17" cy="20" r="1.5" />
            <path d="M5 5h2l1.2 8.4a2 2 0 0 0 2 1.6h6.9a2 2 0 0 0 2-1.6L20 8H9" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    );
}

function UploadIcon({ className }: IconProps) {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className}>
            <path d="M12 16V4" strokeLinecap="round" />
            <path d="M7 9l5-5 5 5" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M5 20h14" strokeLinecap="round" />
        </svg>
    );
}

function ShieldIcon({ className }: IconProps) {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className}>
            <path d="M12 3l8 3v6c0 4.5-3.1 8.6-8 9-4.9-.4-8-4.5-8-9V6l8-3z" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    );
}

function AlertIcon({ className }: IconProps) {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className}>
            <circle cx="12" cy="12" r="9" />
            <path d="M12 7v5" strokeLinecap="round" />
            <circle cx="12" cy="16" r="0.5" fill="currentColor" stroke="none" />
        </svg>
    );
}

function CashIcon({ className }: IconProps) {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className}>
            <rect x="3" y="6" width="18" height="12" rx="2" />
            <circle cx="12" cy="12" r="2.5" />
            <path d="M7 9h0.01M17 15h0.01" strokeLinecap="round" />
        </svg>
    );
}
