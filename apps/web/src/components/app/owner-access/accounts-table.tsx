
'use client';

import { useState } from 'react';
import type { UserAccount } from '@/types/owner-access';
import { RoleBadge, StatusBadge } from './shared-components';
import { ResetPasswordModal } from './reset-password-modal';
import { ChangeRoleModal, ConfirmActionModal } from './member-actions-modals';

type ModalAction = 'reset' | 'role' | 'suspend' | 'remove';

interface AccountsTableProps {
    accounts: UserAccount[];
    onRefresh?: () => void;
}

export function AccountsTable({ accounts, onRefresh }: AccountsTableProps) {
    const [selectedUser, setSelectedUser] = useState<UserAccount | null>(null);
    const [activeModal, setActiveModal] = useState<ModalAction | null>(null);

    const openModal = (user: UserAccount, action: ModalAction) => {
        setSelectedUser(user);
        setActiveModal(action);
    };

    const handleModalClose = () => {
        setActiveModal(null);
        setSelectedUser(null);
        onRefresh?.();
    };

    if (accounts.length === 0) {
        return (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-8 text-center">
                <p className="text-sm text-slate-600">No hay cuentas registradas</p>
            </div>
        );
    }

    return (
        <>
            <div className="overflow-hidden rounded-lg border border-slate-200">
                <table className="min-w-full divide-y divide-slate-200">
                    <thead className="bg-slate-50">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                                Usuario
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                                Rol
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                                Estado
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                                Credenciales
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                                Último acceso
                            </th>
                            <th className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wide text-slate-500">
                                Acciones
                            </th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 bg-white">
                        {accounts.map((account) => (
                            <AccountRow key={account.id} account={account} onAction={openModal} />
                        ))}
                    </tbody>
                </table>
            </div>

            {selectedUser && activeModal === 'reset' && (
                <ResetPasswordModal
                    isOpen
                    onClose={handleModalClose}
                    user={selectedUser}
                />
            )}
            {selectedUser && activeModal === 'role' && (
                <ChangeRoleModal
                    isOpen
                    onClose={handleModalClose}
                    user={selectedUser}
                />
            )}
            {selectedUser && (activeModal === 'suspend' || activeModal === 'remove') && (
                <ConfirmActionModal
                    isOpen
                    onClose={handleModalClose}
                    user={selectedUser}
                    action={activeModal}
                />
            )}
        </>
    );
}

interface AccountRowProps {
    account: UserAccount;
    onAction: (user: UserAccount, action: ModalAction) => void;
}

function AccountRow({ account, onAction }: AccountRowProps) {
    const lastLogin = account.last_login
        ? new Date(account.last_login).toLocaleDateString('es-AR', {
            day: '2-digit',
            month: 'short',
            year: 'numeric',
        })
        : 'Nunca';

    const isOwner = account.role === 'owner';
    const isSuspended = account.membership_status === 'suspended';

    return (
        <tr className={`hover:bg-slate-50 ${isSuspended ? 'opacity-60' : ''}`}>
            <td className="px-6 py-4">
                <div className="flex flex-col">
                    <div className="text-sm font-medium text-slate-900">{account.full_name}</div>
                    <div className="text-xs text-slate-500">
                        {account.email || account.username}
                    </div>
                    {account.email && account.username !== account.email && (
                        <div className="text-xs text-slate-400">@{account.username}</div>
                    )}
                </div>
            </td>
            <td className="px-6 py-4">
                <RoleBadge role={account.role} roleDisplay={account.role_display} size="sm" />
            </td>
            <td className="px-6 py-4">
                {isSuspended ? (
                    <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
                        <span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-amber-500"></span>
                        Suspendido
                    </span>
                ) : (
                    <StatusBadge isActive={account.is_active} size="sm" />
                )}
            </td>
            <td className="px-6 py-4">
                {account.has_usable_password ? (
                    <span className="inline-flex items-center text-xs text-green-700">
                        <svg className="mr-1 h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                            />
                        </svg>
                        Configurada
                    </span>
                ) : (
                    <span className="inline-flex items-center text-xs text-amber-600">
                        <svg className="mr-1 h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                            />
                        </svg>
                        Sin contraseña
                    </span>
                )}
            </td>
            <td className="px-6 py-4 text-sm text-slate-600">{lastLogin}</td>
            <td className="px-6 py-4">
                <div className="flex items-center justify-end gap-1">
                    {!isOwner && (
                        <button
                            onClick={() => onAction(account, 'role')}
                            className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 transition-colors"
                            title="Cambiar rol"
                        >
                            Rol
                        </button>
                    )}
                    <button
                        onClick={() => onAction(account, 'reset')}
                        className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-50 transition-colors"
                        title="Resetear contraseña"
                    >
                        Resetear
                    </button>
                    {!isOwner && (
                        <>
                            <button
                                onClick={() => onAction(account, 'suspend')}
                                className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
                                    isSuspended
                                        ? 'text-green-700 hover:bg-green-50'
                                        : 'text-amber-700 hover:bg-amber-50'
                                }`}
                                title={isSuspended ? 'Reactivar' : 'Suspender'}
                            >
                                {isSuspended ? 'Reactivar' : 'Suspender'}
                            </button>
                            <button
                                onClick={() => onAction(account, 'remove')}
                                className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 transition-colors"
                                title="Eliminar del negocio"
                            >
                                Eliminar
                            </button>
                        </>
                    )}
                </div>
            </td>
        </tr>
    );
}
