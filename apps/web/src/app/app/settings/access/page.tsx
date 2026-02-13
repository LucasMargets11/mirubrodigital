/**
 * Owner Access Management - Main Page
 * Accessible from Settings for OWNER role only
 */
'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ownerAccessApi } from '@/lib/api/owner-access';
import type { AccessSummary, RoleSummary, UserAccount } from '@/types/owner-access';
import { PermissionList, EmptyState } from '@/components/app/owner-access/shared-components';
import { AccountsTable } from '@/components/app/owner-access/accounts-table';

type Tab = 'my-roles' | 'business-roles' | 'accounts';

export default function OwnerAccessPage() {
    const [activeTab, setActiveTab] = useState<Tab>('my-roles');
    const [accessSummary, setAccessSummary] = useState<AccessSummary | null>(null);
    const [roles, setRoles] = useState<RoleSummary[]>([]);
    const [accounts, setAccounts] = useState<UserAccount[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isOwner, setIsOwner] = useState(false);

    useEffect(() => {
        loadAccessSummary();
    }, []);

    const loadAccessSummary = async () => {
        try {
            setIsLoading(true);
            setError(null);
            const summary = await ownerAccessApi.getAccessSummary();
            setAccessSummary(summary);
            setIsOwner(summary.role === 'owner');

            if (summary.role === 'owner') {
                // Load additional data for owner
                const [rolesData, accountsData] = await Promise.all([
                    ownerAccessApi.getRoles(),
                    ownerAccessApi.getAccounts(),
                ]);
                setRoles(rolesData);
                setAccounts(accountsData);
            }
        } catch (err: any) {
            setError(err.message || 'Error al cargar información de accesos');
        } finally {
            setIsLoading(false);
        }
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
        );
    }

    if (!accessSummary) {
        return (
            <EmptyState
                title="No se pudo cargar la información"
                description="No se encontró información de acceso para tu cuenta."
            />
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <header>
                <h1 className="text-2xl font-semibold text-slate-900">Roles & Accesos</h1>
                <p className="mt-1 text-sm text-slate-600">
                    {isOwner
                        ? 'Administra roles, permisos y cuentas de usuarios en tu negocio.'
                        : 'Consulta tus roles y permisos asignados.'}
                </p>
            </header>

            {/* Tabs Navigation */}
            <div className="border-b border-slate-200">
                <nav className="flex gap-6">
                    <button
                        onClick={() => setActiveTab('my-roles')}
                        className={`border-b-2 pb-3 text-sm font-medium transition-colors ${activeTab === 'my-roles'
                            ? 'border-blue-600 text-blue-600'
                            : 'border-transparent text-slate-600 hover:text-slate-900'
                            }`}
                    >
                        Mis Roles
                    </button>
                    {isOwner && (
                        <>
                            <button
                                onClick={() => setActiveTab('business-roles')}
                                className={`border-b-2 pb-3 text-sm font-medium transition-colors ${activeTab === 'business-roles'
                                    ? 'border-blue-600 text-blue-600'
                                    : 'border-transparent text-slate-600 hover:text-slate-900'
                                    }`}
                            >
                                Roles del Negocio
                            </button>
                            <button
                                onClick={() => setActiveTab('accounts')}
                                className={`border-b-2 pb-3 text-sm font-medium transition-colors ${activeTab === 'accounts'
                                    ? 'border-blue-600 text-blue-600'
                                    : 'border-transparent text-slate-600 hover:text-slate-900'
                                    }`}
                            >
                                Accesos (Cuentas)
                            </button>
                        </>
                    )}
                </nav>
            </div>

            {/* Tab Content */}
            <div className="rounded-xl border border-slate-200 bg-white p-6">
                {activeTab === 'my-roles' && <MyRolesTab summary={accessSummary} />}
                {activeTab === 'business-roles' && isOwner && <BusinessRolesTab roles={roles} />}
                {activeTab === 'accounts' && isOwner && <AccountsTab accounts={accounts} onRefresh={loadAccessSummary} />}
            </div>
        </div>
    );
}

function MyRolesTab({ summary }: { summary: AccessSummary }) {
    return (
        <div className="space-y-6">
            {/* User Info */}
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-sm font-medium text-slate-900">{summary.business_name}</p>
                        <p className="text-xs text-slate-500">Servicio: {summary.service}</p>
                    </div>
                    <div className="text-right">
                        <span className="inline-flex items-center rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-sm font-medium text-blue-700">
                            {summary.role_display}
                        </span>
                    </div>
                </div>
            </div>

            {/* Permissions */}
            <div>
                <h2 className="mb-4 text-lg font-semibold text-slate-900">Mis Permisos</h2>
                <PermissionList permissionsByModule={summary.permissions_by_module} />
            </div>
        </div>
    );
}

function BusinessRolesTab({ roles }: { roles: RoleSummary[] }) {
    if (roles.length === 0) {
        return (
            <EmptyState
                title="No hay roles configurados"
                description="No se encontraron roles en el negocio."
            />
        );
    }

    return (
        <div className="space-y-4">
            <h2 className="text-lg font-semibold text-slate-900">Roles Disponibles</h2>
            <p className="text-sm text-slate-600">
                Haz clic en un rol para ver sus permisos y usuarios asignados
            </p>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {roles.map((role) => (
                    <Link
                        key={role.role}
                        href={`/app/settings/access/roles/${role.role}`}
                        className="group rounded-lg border border-slate-200 bg-white p-4 hover:border-blue-300 hover:shadow-md transition-all cursor-pointer"
                    >
                        <div className="flex items-start justify-between">
                            <h3 className="text-sm font-semibold text-slate-900 group-hover:text-blue-700 transition-colors">
                                {role.role_display}
                            </h3>
                            <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700 group-hover:bg-blue-100 group-hover:text-blue-700 transition-colors">
                                {role.user_count} usuarios
                            </span>
                        </div>
                        <p className="mt-2 text-xs text-slate-600">{role.permission_count} permisos incluidos</p>
                        <div className="mt-3 flex items-center text-xs text-blue-600 opacity-0 group-hover:opacity-100 transition-opacity">
                            Ver detalles
                            <svg className="ml-1 h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                            </svg>
                        </div>
                    </Link>
                ))}
            </div>
        </div>
    );
}

function AccountsTab({ accounts, onRefresh }: { accounts: UserAccount[]; onRefresh: () => void }) {
    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-slate-900">Cuentas de Usuario</h2>
                <button
                    onClick={onRefresh}
                    className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
                >
                    Actualizar
                </button>
            </div>
            <AccountsTable accounts={accounts} onRefresh={onRefresh} />
        </div>
    );
}
