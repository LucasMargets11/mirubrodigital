'use client';

import { FormEvent, useState } from 'react';
import { forgotPassword } from '@/lib/auth/client';

type PageState = 'form' | 'sent';

export default function OlvidarContrasenaPage() {
    const [email, setEmail] = useState('');
    const [pageState, setPageState] = useState<PageState>('form');
    const [error, setError] = useState<string | null>(null);
    const [isSubmitting, setIsSubmitting] = useState(false);

    const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        setError(null);
        setIsSubmitting(true);

        const result = await forgotPassword(email);
        if (!result.success) {
            setError(result.message ?? 'Hubo un error. Por favor intentá de nuevo.');
            setIsSubmitting(false);
            return;
        }

        setPageState('sent');
    };

    return (
        <section className="min-h-full flex items-center justify-center py-16 px-6">
            <div className="w-full max-w-md mx-auto">
                <div className="rounded-3xl border border-slate-200 bg-white/80 p-10 shadow-xl shadow-brand-500/5 space-y-6">
                    {pageState === 'form' ? (
                        <>
                            <div className="text-center space-y-2">
                                <h1 className="text-2xl font-display font-bold text-slate-900">
                                    Recuperar contraseña
                                </h1>
                                <p className="text-sm text-slate-600">
                                    Ingresá tu email y te enviamos un enlace para crear una nueva contraseña.
                                </p>
                            </div>

                            <form onSubmit={handleSubmit} className="space-y-5">
                                <div>
                                    <label htmlFor="email" className="text-sm font-medium text-slate-700">
                                        Email
                                    </label>
                                    <input
                                        id="email"
                                        type="email"
                                        required
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                                        placeholder="tu@empresa.com"
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
                                    {isSubmitting ? 'Enviando…' : 'Enviar enlace'}
                                </button>

                                <div className="text-center">
                                    <a href="/entrar" className="text-sm text-slate-500 hover:text-brand-600 hover:underline">
                                        Volver al inicio de sesión
                                    </a>
                                </div>
                            </form>
                        </>
                    ) : (
                        <div className="text-center space-y-4">
                            <div className="mx-auto h-12 w-12 rounded-full bg-green-100 flex items-center justify-center">
                                <svg className="h-6 w-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                                </svg>
                            </div>
                            <h2 className="text-xl font-display font-bold text-slate-900">
                                Revisá tu casilla
                            </h2>
                            <p className="text-sm text-slate-600">
                                Si el email <strong>{email}</strong> está registrado, vas a recibir un enlace para restablecer tu contraseña en los próximos minutos.
                            </p>
                            <p className="text-xs text-slate-400">
                                El enlace expira en 2 horas. Revisá también tu carpeta de spam.
                            </p>
                            <a href="/entrar" className="block text-sm text-brand-600 hover:underline mt-2">
                                Volver al inicio de sesión
                            </a>
                        </div>
                    )}
                </div>
            </div>
        </section>
    );
}
