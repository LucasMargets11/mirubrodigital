'use client';

import { useState } from 'react';
import { ownerAccessApi } from '@/lib/api/owner-access';
import type { UserAccount } from '@/types/owner-access';

/* ─── Change Role Modal ─── */
interface ChangeRoleModalProps {
    isOpen: boolean;
    onClose: () => void;
    user: UserAccount;
}

const ROLE_OPTIONS: { value: string; label: string }[] = [
    { value: 'admin', label: 'Admin' },
    { value: 'manager', label: 'Manager / Encargado' },
    { value: 'cashier', label: 'Cashier / Caja' },
    { value: 'staff', label: 'Staff / Empleado' },
    { value: 'viewer', label: 'Solo lectura' },
    { value: 'kitchen', label: 'Cocina' },
    { value: 'salon', label: 'Salon / Toma pedidos' },
    { value: 'analyst', label: 'Analyst' },
];

export function ChangeRoleModal({ isOpen, onClose, user }: ChangeRoleModalProps) {
    const [role, setRole] = useState(user.role);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    if (!isOpen) return null;

    const handleSubmit = async () => {
        if (role === user.role) { onClose(); return; }
        setIsLoading(true);
        setError(null);
        try {
            await ownerAccessApi.changeRole(user.id, role);
            onClose();
        } catch (err: any) {
            setError(err.message || 'Error al cambiar rol');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
            <div className="max-w-md w-full rounded-xl bg-white shadow-2xl">
                <div className="border-b border-slate-200 px-6 py-4">
                    <h2 className="text-lg font-semibold text-slate-900">Cambiar Rol</h2>
                </div>
                <div className="px-6 py-4 space-y-4">
                    <p className="text-sm text-slate-600">
                        Cambiar el rol de <strong>{user.full_name}</strong>
                    </p>
                    <select
                        value={role}
                        onChange={(e) => setRole(e.target.value)}
                        className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                    >
                        {ROLE_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                    </select>
                    {error && (
                        <div className="rounded-lg border border-red-200 bg-red-50 p-3">
                            <p className="text-sm text-red-800">{error}</p>
                        </div>
                    )}
                </div>
                <div className="border-t border-slate-200 px-6 py-4 flex justify-end gap-3">
                    <button onClick={onClose} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors" disabled={isLoading}>
                        Cancelar
                    </button>
                    <button onClick={handleSubmit} disabled={isLoading || role === user.role} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors">
                        {isLoading ? 'Guardando...' : 'Guardar'}
                    </button>
                </div>
            </div>
        </div>
    );
}

/* ─── Confirm Action Modal (suspend / remove) ─── */
interface ConfirmActionModalProps {
    isOpen: boolean;
    onClose: () => void;
    user: UserAccount;
    action: 'suspend' | 'remove';
}

export function ConfirmActionModal({ isOpen, onClose, user, action }: ConfirmActionModalProps) {
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    if (!isOpen) return null;

    const isSuspended = user.membership_status === 'suspended';
    const title = action === 'remove'
        ? 'Eliminar Usuario'
        : isSuspended ? 'Reactivar Usuario' : 'Suspender Usuario';
    const description = action === 'remove'
        ? `¿Estás seguro de que deseas eliminar a "${user.full_name}" del negocio? Esta acción no se puede deshacer.`
        : isSuspended
            ? `¿Deseas reactivar el acceso de "${user.full_name}"?`
            : `¿Deseas suspender el acceso de "${user.full_name}"? Podrás reactivarlo después.`;
    const buttonLabel = action === 'remove'
        ? 'Eliminar'
        : isSuspended ? 'Reactivar' : 'Suspender';
    const buttonColor = action === 'remove'
        ? 'bg-red-600 hover:bg-red-700'
        : isSuspended ? 'bg-green-600 hover:bg-green-700' : 'bg-amber-600 hover:bg-amber-700';

    const handleConfirm = async () => {
        setIsLoading(true);
        setError(null);
        try {
            if (action === 'remove') {
                await ownerAccessApi.removeMember(user.id);
            } else {
                await ownerAccessApi.suspendMember(user.id);
            }
            onClose();
        } catch (err: any) {
            setError(err.message || 'Error al realizar la acción');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
            <div className="max-w-md w-full rounded-xl bg-white shadow-2xl">
                <div className="border-b border-slate-200 px-6 py-4">
                    <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
                </div>
                <div className="px-6 py-4 space-y-4">
                    <p className="text-sm text-slate-600">{description}</p>
                    {error && (
                        <div className="rounded-lg border border-red-200 bg-red-50 p-3">
                            <p className="text-sm text-red-800">{error}</p>
                        </div>
                    )}
                </div>
                <div className="border-t border-slate-200 px-6 py-4 flex justify-end gap-3">
                    <button onClick={onClose} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors" disabled={isLoading}>
                        Cancelar
                    </button>
                    <button onClick={handleConfirm} disabled={isLoading} className={`rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50 transition-colors ${buttonColor}`}>
                        {isLoading ? 'Procesando...' : buttonLabel}
                    </button>
                </div>
            </div>
        </div>
    );
}
