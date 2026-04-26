'use client';
export const dynamic = 'force-dynamic';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { verifyEmail } from '@/lib/auth/client';

type State = 'verifying' | 'success' | 'error';

function VerificarEmailContent() {
    const searchParams = useSearchParams();
    const token = searchParams.get('token');
    const [state, setState] = useState<State>('verifying');
    const [errorMessage, setErrorMessage] = useState<string>('');

    useEffect(() => {
        if (!token) {
            setState('error');
            setErrorMessage('Enlace inválido. No se encontró el token de verificación.');
            return;
        }

        verifyEmail(token).then((result) => {
            if (result.success) {
                setState('success');
            } else {
                setState('error');
                setErrorMessage(result.message ?? 'El enlace no es válido o ya expiró.');
            }
        });
    }, [token]);

    return (
        <section className="min-h-full flex items-center justify-center py-16 px-6">
            <div className="w-full max-w-md mx-auto">
                <div className="rounded-3xl border border-slate-200 bg-white/80 p-10 shadow-xl shadow-brand-500/5 text-center space-y-6">
                    {state === 'verifying' && (
                        <>
                            <div className="mx-auto h-12 w-12 rounded-full bg-brand-100 flex items-center justify-center">
                                <svg className="animate-spin h-6 w-6 text-brand-600" fill="none" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 100 16v-4l-3 3 3 3v-4a8 8 0 01-8-8z" />
                                </svg>
                            </div>
                            <h1 className="text-xl font-display font-bold text-slate-900">Verificando tu email…</h1>
                        </>
                    )}

                    {state === 'success' && (
                        <>
                            <div className="mx-auto h-12 w-12 rounded-full bg-green-100 flex items-center justify-center">
                                <svg className="h-6 w-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                                </svg>
                            </div>
                            <h1 className="text-xl font-display font-bold text-slate-900">¡Email verificado!</h1>
                            <p className="text-slate-600 text-sm">Tu cuenta está activa. Podés ingresar al panel.</p>
                            <a
                                href="/entrar"
                                className="inline-block mt-2 rounded-full bg-brand-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 transition-colors"
                            >
                                Ingresar
                            </a>
                        </>
                    )}

                    {state === 'error' && (
                        <>
                            <div className="mx-auto h-12 w-12 rounded-full bg-red-100 flex items-center justify-center">
                                <svg className="h-6 w-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </div>
                            <h1 className="text-xl font-display font-bold text-slate-900">Verificación fallida</h1>
                            <p className="text-slate-600 text-sm">{errorMessage}</p>
                            <div className="space-y-2">
                                <a
                                    href="/entrar"
                                    className="block text-sm text-brand-600 hover:underline"
                                >
                                    Volver al inicio de sesión
                                </a>
                            </div>
                        </>
                    )}
                </div>
            </div>
        </section>
    );
}


export default function VerificarEmailPage() {
    return (
        <Suspense fallback={<div className="min-h-full flex items-center justify-center py-16 px-6">Cargando…</div>}>
            <VerificarEmailContent />
        </Suspense>
    );
}
