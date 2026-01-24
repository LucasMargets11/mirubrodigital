"use client";

import Link from 'next/link';

import type { DashboardFeatures, DashboardPermissions } from '../dashboard-client';
import type { InventorySummaryStats } from '@/features/gestion/types';
import { cn } from '@/lib/utils';

type LaunchChecklistProps = {
    summary: InventorySummaryStats | null;
    permissions: DashboardPermissions;
    features: DashboardFeatures;
    planName: string;
};

type ChecklistItem = {
    key: string;
    label: string;
    description: string;
    href?: string;
    status: 'done' | 'warning' | 'pending' | 'upcoming';
    disabled?: boolean;
};

const STATUS_STYLES: Record<ChecklistItem['status'], { badge: string; icon: string }> = {
    done: { badge: 'bg-emerald-100 text-emerald-700', icon: '✅' },
    warning: { badge: 'bg-amber-100 text-amber-700', icon: '⚠️' },
    pending: { badge: 'bg-slate-100 text-slate-600', icon: '⏳' },
    upcoming: { badge: 'bg-slate-200 text-slate-500', icon: '🚧' },
};

export function LaunchChecklist({ summary, permissions, features, planName }: LaunchChecklistProps) {
    const stockHealthy = (summary?.low_stock ?? 0) === 0 && (summary?.out_of_stock ?? 0) === 0;
    const canAccessCash = permissions.canViewCash && features.cash;

    const items: ChecklistItem[] = [
        {
            key: 'roles',
            label: 'Roles y permisos asignados',
            description: 'Tu equipo ya puede operar en Mirubro.',
            href: '/app/settings',
            status: 'done',
        },
        {
            key: 'plan',
            label: 'Plan activo',
            description: `Plan actual: ${planName || 'N/D'}`,
            href: '/app/planes',
            status: 'done',
        },
        {
            key: 'costs',
            label: 'Costos cargados en productos',
            description: features.products ? 'Asegurate de tener precios y costos para tus reportes.' : 'Activá productos para editar costos.',
            href: features.products ? '/app/gestion/productos' : undefined,
            status: permissions.canManageProducts && features.products ? 'pending' : 'upcoming',
        },
        {
            key: 'stock-min',
            label: 'Stock mínimo configurado',
            description: stockHealthy ? 'Alertas listas. Todo en verde.' : 'Definí mínimos para evitar quiebres.',
            href: features.inventory ? '/app/gestion/stock' : undefined,
            status: stockHealthy ? 'done' : features.inventory ? 'warning' : 'upcoming',
        },
        {
            key: 'cash',
            label: 'Caja operativa',
            description: canAccessCash ? 'Ingresá cobros y controlá tu caja diaria.' : 'Activá caja para registrar movimientos.',
            href: canAccessCash ? '/app/operacion/caja' : undefined,
            status: canAccessCash ? 'pending' : 'upcoming',
            disabled: !canAccessCash,
        },
    ];

    return (
        <section className="space-y-3 rounded-3xl border border-slate-100 bg-white p-5 shadow-sm">
            <div>
                <h2 className="text-lg font-semibold text-slate-900">Checklist de lanzamiento</h2>
                <p className="text-sm text-slate-500">Mantené al día la configuración clave del negocio.</p>
            </div>
            <div className="space-y-3">
                {items.map((item) => (
                    <ChecklistCard key={item.key} item={item} />
                ))}
            </div>
        </section>
    );
}

type ChecklistCardProps = {
    item: ChecklistItem;
};

function ChecklistCard({ item }: ChecklistCardProps) {
    const { label, description, href, status, disabled } = item;
    const styles = STATUS_STYLES[status];
    const content = (
        <div
            className={cn(
                'flex items-center justify-between gap-4 rounded-2xl border border-slate-100 bg-slate-50/80 p-4 transition hover:border-slate-200',
                disabled && 'cursor-not-allowed opacity-70'
            )}
        >
            <div>
                <div className="flex items-center gap-2">
                    <span className="text-lg" aria-hidden="true">
                        {styles.icon}
                    </span>
                    <p className="text-sm font-semibold text-slate-900">{label}</p>
                </div>
                <p className="text-xs text-slate-500">{description}</p>
            </div>
            <span className={cn('rounded-full px-3 py-1 text-xs font-semibold', styles.badge)}>
                {statusLabel(status)}
            </span>
        </div>
    );

    if (href && !disabled) {
        return (
            <Link href={href} className="block">
                {content}
            </Link>
        );
    }
    return content;
}

function statusLabel(status: ChecklistItem['status']) {
    switch (status) {
        case 'done':
            return 'Completado';
        case 'warning':
            return 'Revisar';
        case 'pending':
            return 'En progreso';
        default:
            return 'Próximamente';
    }
}
