'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { apiPost } from '@/lib/api/client';

export default function CambiarContrasenaPage() {
    const router = useRouter();
    const [currentPassword, setCurrentPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const validationError = (() => {
        if (!currentPassword || !newPassword || !confirmPassword) return null;
        if (newPassword.length < 8) return 'La nueva contraseña debe tener al menos 8 caracteres.';
        if (newPassword !== confirmPassword) return 'Las contraseñas no coinciden.';
        return null;
    })();

    const isValid =
        currentPassword.length > 0 &&
        newPassword.length >= 8 &&
        confirmPassword.length > 0 &&
        newPassword === confirmPassword;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!isValid) return;

        setIsLoading(true);
        setError(null);

        try {
            await apiPost('/api/v1/auth/force-change-password/', {
                current_password: currentPassword,
                new_password: newPassword,
            });
            router.replace('/app');
        } catch (err: any) {
            setError(err.message || 'Error al cambiar la contraseña.');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <section className="flex-1 flex items-center justify-center">
            <div className="w-full max-w-md mx-auto px-6">
                <div className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
                    <div className="mb-6 text-center">
                        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-blue-100">
                            <svg className="h-6 w-6 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                            </svg>
                        </div>
                        <h1 className="text-xl font-semibold text-slate-900">Cambiar contraseña</h1>
                        <p className="mt-2 text-sm text-slate-600">
                            El dueño del negocio te asignó una contraseña temporal. Elegí una nueva contraseña para continuar.
                        </p>
                    </div>

                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div>
                            <label htmlFor="current_password" className="block text-sm font-medium text-slate-700">
                                Contraseña actual
                            </label>
                            <input
                                id="current_password"
                                type="password"
                                value={currentPassword}
                                onChange={(e) => setCurrentPassword(e.target.value)}
                                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                                required
                                autoComplete="current-password"
                            />
                        </div>

                        <div>
                            <label htmlFor="new_password" className="block text-sm font-medium text-slate-700">
                                Nueva contraseña
                            </label>
                            <input
                                id="new_password"
                                type="password"
                                value={newPassword}
                                onChange={(e) => setNewPassword(e.target.value)}
                                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                                minLength={8}
                                required
                                autoComplete="new-password"
                            />
                            <p className="mt-1 text-xs text-slate-500">Mínimo 8 caracteres</p>
                        </div>

                        <div>
                            <label htmlFor="confirm_password" className="block text-sm font-medium text-slate-700">
                                Confirmar nueva contraseña
                            </label>
                            <input
                                id="confirm_password"
                                type="password"
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                                required
                                autoComplete="new-password"
                            />
                        </div>

                        {validationError && (
                            <p className="text-sm text-amber-600">{validationError}</p>
                        )}

                        {error && (
                            <div className="rounded-lg border border-red-200 bg-red-50 p-3">
                                <p className="text-sm text-red-800">{error}</p>
                            </div>
                        )}

                        <button
                            type="submit"
                            disabled={isLoading || !isValid}
                            className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                            {isLoading ? 'Guardando...' : 'Cambiar contraseña'}
                        </button>
                    </form>
                </div>
            </div>
        </section>
    );
}
