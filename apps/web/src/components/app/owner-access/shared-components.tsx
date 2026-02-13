/**
 * Shared components for Owner Access Management
 */
'use client';

import type { Capability, PermissionsByModule } from '@/types/owner-access';

interface PermissionListProps {
    permissionsByModule: PermissionsByModule;
    showAllModules?: boolean;
}

export function PermissionList({ permissionsByModule, showAllModules = true }: PermissionListProps) {
    const modules = Object.keys(permissionsByModule).sort();

    if (modules.length === 0) {
        return (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-center text-sm text-slate-500">
                No hay permisos asignados a este rol
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {modules.map((module) => {
                const capabilities = permissionsByModule[module];
                if (!capabilities || capabilities.length === 0) return null;

                return (
                    <div key={module} className="space-y-3">
                        <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">{module}</h3>
                        <div className="space-y-2">
                            {capabilities.map((cap) => (
                                <PermissionItem key={cap.code} capability={cap} />
                            ))}
                        </div>
                    </div>
                );
            })}
        </div>
    );
}

interface PermissionItemProps {
    capability: Capability;
}

function PermissionItem({ capability }: PermissionItemProps) {
    const isGranted = capability.granted !== undefined ? capability.granted : true;

    return (
        <div className="flex items-start gap-3 rounded-lg border border-slate-200 bg-white p-3">
            <div
                className={`mt-0.5 h-5 w-5 rounded-full flex items-center justify-center flex-shrink-0 ${isGranted ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-400'
                    }`}
            >
                {isGranted ? (
                    <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                ) : (
                    <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                )}
            </div>
            <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                    <h4 className="text-sm font-medium text-slate-900">{capability.title}</h4>
                    <code className="text-xs text-slate-400 font-mono">{capability.code}</code>
                </div>
                <p className="mt-1 text-sm text-slate-600">{capability.description}</p>
            </div>
        </div>
    );
}

interface RoleBadgeProps {
    role: string;
    roleDisplay: string;
    size?: 'sm' | 'md';
}

export function RoleBadge({ role, roleDisplay, size = 'md' }: RoleBadgeProps) {
    const colors: Record<string, string> = {
        owner: 'bg-purple-100 text-purple-700 border-purple-200',
        admin: 'bg-blue-100 text-blue-700 border-blue-200',
        manager: 'bg-indigo-100 text-indigo-700 border-indigo-200',
        cashier: 'bg-green-100 text-green-700 border-green-200',
        staff: 'bg-slate-100 text-slate-700 border-slate-200',
        viewer: 'bg-gray-100 text-gray-600 border-gray-200',
        kitchen: 'bg-orange-100 text-orange-700 border-orange-200',
        salon: 'bg-cyan-100 text-cyan-700 border-cyan-200',
        analyst: 'bg-yellow-100 text-yellow-700 border-yellow-200',
    };

    const colorClass = colors[role] || 'bg-slate-100 text-slate-700 border-slate-200';
    const sizeClass = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm';

    return (
        <span className={`inline-flex items-center rounded-full border font-medium ${colorClass} ${sizeClass}`}>
            {roleDisplay}
        </span>
    );
}

interface StatusBadgeProps {
    isActive: boolean;
    size?: 'sm' | 'md';
}

export function StatusBadge({ isActive, size = 'md' }: StatusBadgeProps) {
    const sizeClass = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm';

    if (isActive) {
        return (
            <span className={`inline-flex items-center rounded-full border bg-green-50 text-green-700 border-green-200 font-medium ${sizeClass}`}>
                <span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-green-600"></span>
                Activo
            </span>
        );
    }

    return (
        <span className={`inline-flex items-center rounded-full border bg-red-50 text-red-700 border-red-200 font-medium ${sizeClass}`}>
            <span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-red-600"></span>
            Inactivo
        </span>
    );
}

interface EmptyStateProps {
    title: string;
    description: string;
    icon?: React.ReactNode;
}

export function EmptyState({ title, description, icon }: EmptyStateProps) {
    return (
        <div className="rounded-xl border-2 border-dashed border-slate-200 bg-slate-50 p-12 text-center">
            {icon && <div className="mx-auto mb-4 h-12 w-12 text-slate-400">{icon}</div>}
            <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
            <p className="mt-2 text-sm text-slate-600">{description}</p>
        </div>
    );
}
