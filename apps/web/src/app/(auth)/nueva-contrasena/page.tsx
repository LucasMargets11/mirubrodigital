'use client';
export const dynamic = 'force-dynamic';

import { FormEvent, Suspense, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { resetPassword } from '@/lib/auth/client';

type PageState = 'form' | 'success' | 'invalid';

function NuevaContrasenaContent() {
    const searchParams = useSearchParams();
    const token = searchParams.get('token');

    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [pageState, setPageState] = useState<PageState>(token ? 'form' : 'invalid');
    const [error, setError] = useState<string | null>(null);
    const [isSubmitting, setIsSubmitting] = useState(false);

    const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        setError(null);

        if (password !== confirmPassword) {
            setError('Las contraseñas no coinciden');
            return;
        }
        if (password.length < 8) {
            setError('La contraseña debe tener al menos 8 caracteres');
            return;
        }

        setIsSubmitting(true);
        const result = await resetPassword(token!, password);

        if (!result.success) {
            setError(result.message ?? 'No pudimos restablecer tu contraseña');
            setIsSubmitting(false);
            return;
        }

        setPageState('success');
    };

    return (
        <section className="min-h-full flex items-center justify-center py-16 px-6">
            <div className="w-full max-w-md mx-auto">
                <div className="rounded-3xl border border-slate-200 bg-white/80 p-10 shadow-xl shadow-brand-500/5 space-y-6">
                    {pageState === 'invalid' && (
                        <div className="text-center space-y-4">
                            <div className="mx-auto h-12 w-12 rounded-full bg-red-100 flex items-center justify-center">
                                <svg className="h-6 w-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                                </svg>
                            </div>
                            <h1 className="text-xl font-display font-bold text-slate-900">Enlace inválido</h1>
                            <p className="text-sm text-slate-600">
                                El enlace para restablecer tu contraseña no es válido o ya fue utilizado.
                            </p>
                            <a href="/olvidar-contrasena" className="block text-sm text-brand-600 hover:underline">
                                Solicitar un nuevo enlace
                            </a>
                        </div>
                    )}

                    {pageState === 'form' && (
                        <>
                            <div className="text-center space-y-2">
                                <h1 className="text-2xl font-display font-bold text-slate-900">
                                    Nueva contraseña
                                </h1>
                                <p className="text-sm text-slate-600">
                                    Elegí una contraseña segura de al menos 8 caracteres.
                                </p>
                            </div>

                            <form onSubmit={handleSubmit} className="space-y-5">
                                <div>
                                    <label htmlFor="password" className="text-sm font-medium text-slate-700">
                                        Nueva contraseña
                                    </label>
                                    <input
                                        id="password"
                                        type="password"
                                        required
                                        minLength={8}
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                                        placeholder="••••••••"
                                    />
                                </div>

                                <div>
                                    <label htmlFor="confirmPassword" className="text-sm font-medium text-slate-700">
                                        Repetir contraseña
                                    </label>
                                    <input
                                        id="confirmPassword"
                                        type="password"
                                        required
                                        value={confirmPassword}
                                        onChange={(e) => setConfirmPassword(e.target.value)}
                                        className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                                        placeholder="••••••••"
                                    />
                                </div>

                                {error && (
                                    <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">
                                        {error}
                                    </div>
                                )}

                                <button
                                    type="submit"
                                    disabled={isSubmitting}
                                    className="w-full rounded-full bg-brand-600 px-6 py-3 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60 transition-colors"
                                >
                                    {isSubmitting ? 'Guardando…' : 'Guardar contraseña'}
                                </button>
                            </form>
                        </>
                    )}

                    {pageState === 'success' && (
                        <div className="text-center space-y-4">
                            <div className="mx-auto h-12 w-12 rounded-full bg-green-100 flex items-center justify-center">
                                <svg className="h-6 w-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                                </svg>
                            </div>
                            <h2 className="text-xl font-display font-bold text-slate-900">
                                ¡Contraseña actualizada!
                            </h2>
                            <p className="text-sm text-slate-600">
                                Tu contraseña fue restablecida exitosamente.
                            </p>
                            <a
                                href="/entrar"
                                className="inline-block mt-2 rounded-full bg-brand-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 transition-colors"
                            >
                                Ingresar
                            </a>
                        </div>
                    )}
                </div>
            </div>
        </section>
    );
}

export default function NuevaContrasenaPage() {
    return (
        <Suspense fallback={<div className="min-h-full flex items-center justify-center py-16 px-6">Cargando…</div>}>
            <NuevaContrasenaContent />
        </Suspense>
    );
}
