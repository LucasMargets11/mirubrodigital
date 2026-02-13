/**
 * Modal for resetting user passwords (owner-only)
 * Shows temporary password ONCE with security warnings
 */
'use client';

import { useState } from 'react';
import { ownerAccessApi } from '@/lib/api/owner-access';
import type { UserAccount } from '@/types/owner-access';

interface ResetPasswordModalProps {
    isOpen: boolean;
    onClose: () => void;
    user: UserAccount;
}

export function ResetPasswordModal({ isOpen, onClose, user }: ResetPasswordModalProps) {
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [temporaryPassword, setTemporaryPassword] = useState<string | null>(null);
    const [copied, setCopied] = useState(false);

    if (!isOpen) return null;

    const handleReset = async () => {
        setIsLoading(true);
        setError(null);
        try {
            const response = await ownerAccessApi.resetPassword(user.id);
            setTemporaryPassword(response.temporary_password || null);
        } catch (err: any) {
            setError(err.message || 'Error al resetear la contraseña');
        } finally {
            setIsLoading(false);
        }
    };

    const handleCopy = async () => {
        if (temporaryPassword) {
            await navigator.clipboard.writeText(temporaryPassword);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }
    };

    const handleClose = () => {
        setTemporaryPassword(null);
        setError(null);
        setCopied(false);
        onClose();
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
            <div className="max-w-lg w-full rounded-xl bg-white shadow-2xl">
                {/* Header */}
                <div className="border-b border-slate-200 px-6 py-4">
                    <div className="flex items-center justify-between">
                        <h2 className="text-lg font-semibold text-slate-900">Resetear Contraseña</h2>
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
                <div className="px-6 py-4 space-y-4">
                    {!temporaryPassword ? (
                        <>
                            {/* Confirmation */}
                            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                                <div className="flex items-start gap-3">
                                    <div className="flex-shrink-0">
                                        <div className="h-10 w-10 rounded-full bg-slate-200 flex items-center justify-center">
                                            <svg className="h-5 w-5 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                <path
                                                    strokeLinecap="round"
                                                    strokeLinejoin="round"
                                                    strokeWidth={2}
                                                    d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
                                                />
                                            </svg>
                                        </div>
                                    </div>
                                    <div className="flex-1">
                                        <p className="text-sm font-medium text-slate-900">{user.full_name}</p>
                                        <p className="text-xs text-slate-500">{user.email}</p>
                                        <p className="mt-1 text-xs text-slate-500">Rol: {user.role_display}</p>
                                    </div>
                                </div>
                            </div>

                            {/* Warning */}
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
                                        <p className="font-medium">Importante</p>
                                        <ul className="mt-2 space-y-1 list-disc list-inside text-xs">
                                            <li>Se generará una contraseña temporal</li>
                                            <li>Se mostrará solo UNA VEZ</li>
                                            <li>Deberás compartirla de forma segura con el usuario</li>
                                            <li>Esta acción quedará registrada en auditoría</li>
                                        </ul>
                                    </div>
                                </div>
                            </div>

                            {error && (
                                <div className="rounded-lg border border-red-200 bg-red-50 p-4">
                                    <p className="text-sm text-red-800">{error}</p>
                                </div>
                            )}
                        </>
                    ) : (
                        <>
                            {/* Success with temporary password */}
                            <div className="rounded-lg border border-green-200 bg-green-50 p-4">
                                <div className="flex gap-3">
                                    <svg className="h-5 w-5 flex-shrink-0 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                    </svg>
                                    <div className="text-sm text-green-800">
                                        <p className="font-medium">Contraseña reseteada exitosamente</p>
                                        <p className="mt-1 text-xs">Comparte esta contraseña con el usuario de forma segura.</p>
                                    </div>
                                </div>
                            </div>

                            {/* Temporary password display */}
                            <div className="space-y-2">
                                <label className="text-xs font-medium text-slate-700 uppercase tracking-wide">
                                    Contraseña Temporal (se muestra solo una vez)
                                </label>
                                <div className="flex gap-2">
                                    <input
                                        type="text"
                                        readOnly
                                        value={temporaryPassword}
                                        className="flex-1 rounded-lg border border-slate-300 bg-white px-4 py-3 font-mono text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    />
                                    <button
                                        onClick={handleCopy}
                                        className={`flex items-center gap-2 rounded-lg px-4 py-2 font-medium transition-colors ${copied
                                                ? 'bg-green-100 text-green-700'
                                                : 'bg-blue-600 text-white hover:bg-blue-700'
                                            }`}
                                    >
                                        {copied ? (
                                            <>
                                                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                                </svg>
                                                Copiado
                                            </>
                                        ) : (
                                            <>
                                                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path
                                                        strokeLinecap="round"
                                                        strokeLinejoin="round"
                                                        strokeWidth={2}
                                                        d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                                                    />
                                                </svg>
                                                Copiar
                                            </>
                                        )}
                                    </button>
                                </div>
                                <p className="text-xs text-slate-500">
                                    Usuario: <span className="font-mono font-medium">{user.email}</span>
                                </p>
                            </div>

                            {/* Final warning */}
                            <div className="rounded-lg border border-red-200 bg-red-50 p-4">
                                <div className="flex gap-3">
                                    <svg className="h-5 w-5 flex-shrink-0 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            strokeWidth={2}
                                            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                                        />
                                    </svg>
                                    <div className="text-sm text-red-800">
                                        <p className="font-medium">¡ATENCIÓN!</p>
                                        <p className="mt-1 text-xs">
                                            Esta es la única vez que verás esta contraseña. Cópiala ahora y compártela de forma segura con el usuario.
                                            Al cerrar este modal, no podrás recuperarla.
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </>
                    )}
                </div>

                {/* Footer */}
                <div className="border-t border-slate-200 px-6 py-4">
                    <div className="flex justify-end gap-3">
                        {!temporaryPassword ? (
                            <>
                                <button
                                    onClick={handleClose}
                                    disabled={isLoading}
                                    className="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50 transition-colors"
                                >
                                    Cancelar
                                </button>
                                <button
                                    onClick={handleReset}
                                    disabled={isLoading}
                                    className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
                                >
                                    {isLoading ? 'Reseteando...' : 'Confirmar Reset'}
                                </button>
                            </>
                        ) : (
                            <button
                                onClick={handleClose}
                                className="rounded-lg bg-slate-600 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 transition-colors"
                            >
                                Cerrar
                            </button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
