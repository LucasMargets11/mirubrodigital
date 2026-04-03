'use client';

import { useState } from 'react';
import { ownerAccessApi } from '@/lib/api/owner-access';

interface CreateMemberModalProps {
    isOpen: boolean;
    onClose: (created?: boolean) => void;
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

/** Roles that default to 'personal' account mode. */
const PERSONAL_DEFAULT_ROLES = new Set(['admin', 'manager', 'analyst']);

function getRecommendedMode(role: string): 'owner_managed' | 'personal' {
    return PERSONAL_DEFAULT_ROLES.has(role) ? 'personal' : 'owner_managed';
}

export function CreateMemberModal({ isOpen, onClose }: CreateMemberModalProps) {
    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName] = useState('');
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [role, setRole] = useState('staff');
    const [email, setEmail] = useState('');
    const [accountMode, setAccountMode] = useState<'owner_managed' | 'personal'>('owner_managed');
    const [forcePasswordChange, setForcePasswordChange] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [createdInfo, setCreatedInfo] = useState<{ username: string; fullName: string; role: string } | null>(null);

    if (!isOpen) return null;

    const handleRoleChange = (newRole: string) => {
        setRole(newRole);
        const recommended = getRecommendedMode(newRole);
        setAccountMode(recommended);
        setForcePasswordChange(recommended === 'personal');
    };

    const handleAccountModeChange = (mode: 'owner_managed' | 'personal') => {
        setAccountMode(mode);
        if (mode === 'owner_managed') {
            setForcePasswordChange(false);
        }
    };

    if (!isOpen) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError(null);

        try {
            const response = await ownerAccessApi.createMember({
                first_name: firstName.trim(),
                last_name: lastName.trim(),
                username: username.trim(),
                password,
                role,
                account_mode: accountMode,
                force_password_change: accountMode === 'personal' ? forcePasswordChange : false,
                ...(email.trim() ? { email: email.trim() } : {}),
            });
            setCreatedInfo({
                username: response.username,
                fullName: response.full_name,
                role: response.role_display,
            });
        } catch (err: any) {
            setError(err.message || 'Error al crear el usuario');
        } finally {
            setIsLoading(false);
        }
    };

    const handleClose = () => {
        setFirstName('');
        setLastName('');
        setUsername('');
        setPassword('');
        setRole('staff');
        setEmail('');
        setAccountMode('owner_managed');
        setForcePasswordChange(false);
        setError(null);
        setCreatedInfo(null);
        onClose(!!createdInfo);
    };

    const isValid = firstName.trim() && lastName.trim() && username.trim().length >= 3 && password.length >= 8;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
            <div className="max-w-lg w-full rounded-xl bg-white shadow-2xl">
                {/* Header */}
                <div className="border-b border-slate-200 px-6 py-4">
                    <div className="flex items-center justify-between">
                        <h2 className="text-lg font-semibold text-slate-900">Crear Usuario Interno</h2>
                        <button
                            onClick={handleClose}
                            className="text-slate-400 hover:text-slate-600 transition-colors"
                        >
                            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>
                </div>

                {/* Body */}
                <div className="px-6 py-4">
                    {createdInfo ? (
                        /* Success state */
                        <div className="space-y-4">
                            <div className="rounded-lg border border-green-200 bg-green-50 p-4">
                                <div className="flex gap-3">
                                    <svg className="h-5 w-5 flex-shrink-0 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                    </svg>
                                    <div className="text-sm text-green-800">
                                        <p className="font-medium">Usuario creado exitosamente</p>
                                        <p className="mt-1 text-xs">
                                            <strong>{createdInfo.fullName}</strong> ({createdInfo.username}) — {createdInfo.role}
                                        </p>
                                    </div>
                                </div>
                            </div>

                            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                                <div className="flex gap-3">
                                    <svg className="h-5 w-5 flex-shrink-0 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            strokeWidth={2}
                                            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                                        />
                                    </svg>
                                    <div className="text-sm text-amber-800">
                                        <p className="font-medium">Comparte las credenciales de forma segura</p>
                                        <ul className="mt-2 space-y-1 list-disc list-inside text-xs">
                                            <li>Usuario: <strong>{createdInfo.username}</strong></li>
                                            <li>La contraseña ingresada es la que usará para acceder</li>
                                            <li>Puede cambiarse después desde &ldquo;Resetear contraseña&rdquo;</li>
                                        </ul>
                                    </div>
                                </div>
                            </div>
                        </div>
                    ) : (
                        /* Form */
                        <form onSubmit={handleSubmit} className="space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-slate-700">
                                        Nombre <span className="text-red-500">*</span>
                                    </label>
                                    <input
                                        type="text"
                                        value={firstName}
                                        onChange={(e) => setFirstName(e.target.value)}
                                        className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                                        placeholder="Juan"
                                        required
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700">
                                        Apellido <span className="text-red-500">*</span>
                                    </label>
                                    <input
                                        type="text"
                                        value={lastName}
                                        onChange={(e) => setLastName(e.target.value)}
                                        className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                                        placeholder="Pérez"
                                        required
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700">
                                    Usuario (login) <span className="text-red-500">*</span>
                                </label>
                                <input
                                    type="text"
                                    value={username}
                                    onChange={(e) => setUsername(e.target.value.toLowerCase().replace(/[^a-z0-9._-]/g, ''))}
                                    className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                                    placeholder="juan.perez"
                                    minLength={3}
                                    required
                                />
                                <p className="mt-1 text-xs text-slate-500">
                                    Mínimo 3 caracteres. Solo letras, números, puntos, guiones.
                                </p>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700">
                                    Contraseña <span className="text-red-500">*</span>
                                </label>
                                <input
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                                    placeholder="Mínimo 8 caracteres"
                                    minLength={8}
                                    required
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700">
                                    Rol <span className="text-red-500">*</span>
                                </label>
                                <select
                                    value={role}
                                    onChange={(e) => handleRoleChange(e.target.value)}
                                    className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                                >
                                    {ROLE_OPTIONS.map((opt) => (
                                        <option key={opt.value} value={opt.value}>
                                            {opt.label}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700">
                                    Modo de cuenta
                                </label>
                                <div className="mt-1 flex gap-3">
                                    <label className={`flex-1 cursor-pointer rounded-lg border px-3 py-2 text-center text-sm transition-colors ${accountMode === 'owner_managed' ? 'border-blue-500 bg-blue-50 text-blue-700 font-medium' : 'border-slate-300 text-slate-600 hover:bg-slate-50'}`}>
                                        <input
                                            type="radio"
                                            name="account_mode"
                                            value="owner_managed"
                                            checked={accountMode === 'owner_managed'}
                                            onChange={() => handleAccountModeChange('owner_managed')}
                                            className="sr-only"
                                        />
                                        Administrada
                                    </label>
                                    <label className={`flex-1 cursor-pointer rounded-lg border px-3 py-2 text-center text-sm transition-colors ${accountMode === 'personal' ? 'border-blue-500 bg-blue-50 text-blue-700 font-medium' : 'border-slate-300 text-slate-600 hover:bg-slate-50'}`}>
                                        <input
                                            type="radio"
                                            name="account_mode"
                                            value="personal"
                                            checked={accountMode === 'personal'}
                                            onChange={() => handleAccountModeChange('personal')}
                                            className="sr-only"
                                        />
                                        Personal
                                    </label>
                                </div>
                                <p className="mt-1 text-xs text-slate-500">
                                    {accountMode === 'owner_managed'
                                        ? 'Vos gestionás la contraseña. El usuario no puede cambiarla.'
                                        : 'El usuario gestiona su propia contraseña y puede recuperarla por email.'}
                                </p>
                            </div>

                            {accountMode === 'personal' && (
                                <div className="flex items-center gap-2">
                                    <input
                                        type="checkbox"
                                        id="force_password_change"
                                        checked={forcePasswordChange}
                                        onChange={(e) => setForcePasswordChange(e.target.checked)}
                                        className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                                    />
                                    <label htmlFor="force_password_change" className="text-sm text-slate-700">
                                        Forzar cambio de contraseña en el primer inicio de sesión
                                    </label>
                                </div>
                            )}

                            <div>
                                <label className="block text-sm font-medium text-slate-700">
                                    Email <span className="text-xs text-slate-400">(opcional)</span>
                                </label>
                                <input
                                    type="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                                    placeholder="juan@empresa.com"
                                />
                            </div>

                            {error && (
                                <div className="rounded-lg border border-red-200 bg-red-50 p-3">
                                    <p className="text-sm text-red-800">{error}</p>
                                </div>
                            )}

                            <div className="flex justify-end gap-3 pt-2">
                                <button
                                    type="button"
                                    onClick={handleClose}
                                    className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
                                    disabled={isLoading}
                                >
                                    Cancelar
                                </button>
                                <button
                                    type="submit"
                                    disabled={isLoading || !isValid}
                                    className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                >
                                    {isLoading ? 'Creando...' : 'Crear Usuario'}
                                </button>
                            </div>
                        </form>
                    )}
                </div>

                {/* Footer (only for success state) */}
                {createdInfo && (
                    <div className="border-t border-slate-200 px-6 py-4">
                        <div className="flex justify-end">
                            <button
                                onClick={handleClose}
                                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
                            >
                                Cerrar
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
