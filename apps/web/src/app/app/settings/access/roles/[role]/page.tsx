/**
 * Role Detail Page - Owner Access Management
 * Shows detailed permissions and users for a specific role
 * Allows owners to toggle permissions on/off
 */
'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { ownerAccessApi } from '@/lib/api/owner-access';
import type { RoleDetail, PermissionUpdate } from '@/types/owner-access';
import { EmptyState, RoleBadge } from '@/components/app/owner-access/shared-components';
import { AccountsTable } from '@/components/app/owner-access/accounts-table';

export default function RoleDetailPage() {
    const params = useParams();
    const router = useRouter();
    const role = params.role as string;

    const [roleDetail, setRoleDetail] = useState<RoleDetail | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isEditing, setIsEditing] = useState(false);
    const [isSaving, setIsSaving] = useState(false);
    const [pendingChanges, setPendingChanges] = useState<Map<string, boolean>>(new Map());

    const isOwnerRole = role === 'owner';

    useEffect(() => {
        loadRoleDetail();
    }, [role]);

    const loadRoleDetail = async () => {
        try {
            setIsLoading(true);
            setError(null);
            const data = await ownerAccessApi.getRoleDetail(role);
            setRoleDetail(data);
            setPendingChanges(new Map()); // Clear changes on reload
        } catch (err: any) {
            setError(err.message || 'Error al cargar información del rol');
        } finally {
            setIsLoading(false);
        }
    };

    const handleTogglePermission = (permissionCode: string, currentlyEnabled: boolean) => {
        const newChanges = new Map(pendingChanges);
        const newValue = !currentlyEnabled;

        // Check if this matches the original state
        const originallyEnabled = isPermissionCurrentlyEnabled(permissionCode);
        if (newValue === originallyEnabled) {
            // Remove from pending changes if it matches original
            newChanges.delete(permissionCode);
        } else {
            // Add to pending changes
            newChanges.set(permissionCode, newValue);
        }

        setPendingChanges(newChanges);
    };

    const isPermissionCurrentlyEnabled = (permissionCode: string): boolean => {
        if (!roleDetail) return false;

        for (const permissions of Object.values(roleDetail.permissions_by_module)) {
            const found = permissions.find((p: any) => p.code === permissionCode);
            if (found) return found.enabled || false;
        }
        return false;
    };

    const getEffectivePermissionState = (permissionCode: string): boolean => {
        // If there's a pending change, use that
        if (pendingChanges.has(permissionCode)) {
            return pendingChanges.get(permissionCode)!;
        }
        // Otherwise use current state
        return isPermissionCurrentlyEnabled(permissionCode);
    };

    const handleSaveChanges = async () => {
        if (pendingChanges.size === 0) {
            setIsEditing(false);
            return;
        }

        try {
            setIsSaving(true);

            const updates: PermissionUpdate[] = Array.from(pendingChanges.entries()).map(
                ([permission, enabled]) => ({ permission, enabled })
            );

            await ownerAccessApi.updateRolePermissions(role, { permissions: updates });

            // Reload role detail to get updated permissions
            await loadRoleDetail();
            setIsEditing(false);
            setPendingChanges(new Map());
        } catch (err: any) {
            alert(err.message || 'Error al guardar cambios');
        } finally {
            setIsSaving(false);
        }
    };

    const handleCancelEdit = () => {
        setPendingChanges(new Map());
        setIsEditing(false);
    };

    if (isLoading) {
        return (
            <div className="flex items-center justify-center min-h-[400px]">
                <div className="text-center">
                    <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-blue-600 border-r-transparent"></div>
                    <p className="mt-4 text-sm text-slate-600">Cargando...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="space-y-6">
                <button
                    onClick={() => router.back()}
                    className="flex items-center gap-2 text-sm text-slate-600 hover:text-slate-900"
                >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                    </svg>
                    Volver
                </button>
                <div className="rounded-lg border border-red-200 bg-red-50 p-6">
                    <div className="flex gap-3">
                        <svg className="h-5 w-5 flex-shrink-0 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                            />
                        </svg>
                        <div>
                            <h3 className="text-sm font-medium text-red-800">Error</h3>
                            <p className="mt-1 text-sm text-red-700">{error}</p>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    if (!roleDetail) {
        return (
            <EmptyState
                title="Rol no encontrado"
                description="No se pudo cargar la información de este rol."
            />
        );
    }

    return (
        <div className="space-y-6">
            {/* Header with Back Button */}
            <div className="flex items-center justify-between">
                <button
                    onClick={() => router.back()}
                    className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100 transition-colors"
                >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                    </svg>
                    Volver
                </button>

                {/* Edit Controls */}
                {!isOwnerRole && (
                    <div className="flex gap-2">
                        {!isEditing ? (
                            <button
                                onClick={() => setIsEditing(true)}
                                className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
                            >
                                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                                </svg>
                                Editar Permisos
                            </button>
                        ) : (
                            <>
                                <button
                                    onClick={handleCancelEdit}
                                    disabled={isSaving}
                                    className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition-colors"
                                >
                                    Cancelar
                                </button>
                                <button
                                    onClick={handleSaveChanges}
                                    disabled={isSaving || pendingChanges.size === 0}
                                    className="flex items-center gap-2 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                >
                                    {isSaving ? (
                                        <>
                                            <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"></div>
                                            Guardando...
                                        </>
                                    ) : (
                                        <>
                                            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                            </svg>
                                            Guardar Cambios {pendingChanges.size > 0 && `(${pendingChanges.size})`}
                                        </>
                                    )}
                                </button>
                            </>
                        )}
                    </div>
                )}
            </div>

            {/* Role Header */}
            <header className="border-b border-slate-200 pb-6">
                <div className="flex items-center justify-between">
                    <div className="space-y-2">
                        <div className="flex items-center gap-3">
                            <h1 className="text-2xl font-semibold text-slate-900">{roleDetail.role_display}</h1>
                            <RoleBadge role={roleDetail.role} roleDisplay={roleDetail.role_display} />
                        </div>
                        <p className="text-sm text-slate-600">{roleDetail.description}</p>
                        <p className="text-xs text-slate-500">
                            Servicio: <span className="font-medium">{roleDetail.service}</span>
                        </p>
                    </div>

                    <div className="text-right">
                        <div className="text-2xl font-bold text-slate-900">{roleDetail.users.length}</div>
                        <div className="text-xs text-slate-500">usuarios con este rol</div>
                    </div>
                </div>
            </header>

            {isOwnerRole && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                    <div className="flex gap-3">
                        <svg className="h-5 w-5 flex-shrink-0 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <p className="text-sm text-amber-800">
                            El rol <strong>Owner</strong> tiene todos los permisos y no puede ser modificado.
                        </p>
                    </div>
                </div>
            )}

            {/* Permissions Section */}
            <div className="rounded-xl border border-slate-200 bg-white p-6">
                <div className="mb-6 flex items-center justify-between border-b border-slate-200 pb-4">
                    <div>
                        <h2 className="text-lg font-semibold text-slate-900">Permisos y Capacidades</h2>
                        <p className="mt-1 text-sm text-slate-600">
                            {isEditing
                                ? 'Activa o desactiva permisos para este rol'
                                : 'Funcionalidades que este rol puede realizar en el sistema'
                            }
                        </p>
                    </div>
                    <div className="rounded-lg bg-blue-50 px-3 py-1 text-sm font-medium text-blue-700">
                        {Object.values(roleDetail.permissions_by_module)
                            .flat()
                            .filter((p: any) => p.enabled).length}{' '}
                        permisos activos
                    </div>
                </div>

                <EditablePermissionList
                    permissionsByModule={roleDetail.permissions_by_module}
                    service={roleDetail.service}
                    isEditing={isEditing}
                    getEffectiveState={getEffectivePermissionState}
                    onToggle={handleTogglePermission}
                />
            </div>

            {/* Users Section */}
            <div className="rounded-xl border border-slate-200 bg-white p-6">
                <div className="mb-6 border-b border-slate-200 pb-4">
                    <h2 className="text-lg font-semibold text-slate-900">Usuarios con este Rol</h2>
                    <p className="mt-1 text-sm text-slate-600">
                        Cuentas que tienen asignado el rol de {roleDetail.role_display}
                    </p>
                </div>

                {roleDetail.users.length > 0 ? (
                    <AccountsTable accounts={roleDetail.users} onRefresh={loadRoleDetail} />
                ) : (
                    <EmptyState
                        title="Sin usuarios asignados"
                        description={`No hay usuarios con el rol de ${roleDetail.role_display} en este momento.`}
                    />
                )}
            </div>
        </div>
    );
}

// Editable Permission List Component
interface EditablePermissionListProps {
    permissionsByModule: Record<string, any[]>;
    service: string;
    isEditing: boolean;
    getEffectiveState: (code: string) => boolean;
    onToggle: (code: string, currentState: boolean) => void;
}

function EditablePermissionList({
    permissionsByModule,
    service,
    isEditing,
    getEffectiveState,
    onToggle,
}: EditablePermissionListProps) {
    if (Object.keys(permissionsByModule).length === 0) {
        return (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-8 text-center">
                <p className="text-sm text-slate-600">No hay permisos configurados para este rol</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {Object.entries(permissionsByModule).map(([module, permissions]) => {
                // En modo lectura, solo mostrar permisos habilitados
                const visiblePermissions = isEditing
                    ? permissions
                    : permissions.filter((p: any) => p.enabled);

                // Si no hay permisos visibles para este módulo, no mostrar el módulo
                if (visiblePermissions.length === 0) return null;

                return (
                    <div key={module} className="rounded-lg border border-slate-100 bg-slate-50/50 p-4">
                        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-700">
                            {module}
                        </h3>
                        <div className="space-y-2">
                            {visiblePermissions.map((perm: any) => {
                                const isEnabled = getEffectiveState(perm.code);

                                return (
                                    <div
                                        key={perm.code}
                                        className={`flex items-start justify-between rounded-lg p-3 transition-colors ${isEditing
                                            ? 'bg-white border border-slate-200 hover:border-slate-300'
                                            : 'bg-white'
                                            }`}
                                    >
                                        <div className="flex-1">
                                            <div className="flex items-center gap-2">
                                                {!isEditing && (
                                                    <svg
                                                        className="h-4 w-4 flex-shrink-0 text-green-600"
                                                        fill="none"
                                                        viewBox="0 0 24 24"
                                                        stroke="currentColor"
                                                    >
                                                        <path
                                                            strokeLinecap="round"
                                                            strokeLinejoin="round"
                                                            strokeWidth={2}
                                                            d="M5 13l4 4L19 7"
                                                        />
                                                    </svg>
                                                )}
                                                <span className="text-sm font-medium text-slate-900">
                                                    {perm.title}
                                                </span>
                                            </div>
                                            <p className="mt-1 text-xs text-slate-600">{perm.description}</p>
                                            <code className="mt-1 inline-block rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                                                {perm.code}
                                            </code>
                                        </div>

                                        {isEditing && (
                                            <label className="relative inline-flex cursor-pointer items-center">
                                                <input
                                                    type="checkbox"
                                                    checked={isEnabled}
                                                    onChange={() => onToggle(perm.code, isEnabled)}
                                                    className="peer sr-only"
                                                />
                                                <div className="peer h-6 w-11 rounded-full bg-slate-300 after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:border after:border-slate-300 after:bg-white after:transition-all after:content-[''] peer-checked:bg-blue-600 peer-checked:after:translate-x-full peer-checked:after:border-white peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300"></div>
                                            </label>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                );
            })}
        </div>
    );
}
