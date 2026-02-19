'use client';

import { FormEvent, useState } from 'react';
import { login, register } from '@/lib/auth/client';
import { cn } from '@/lib/utils';

type AuthMode = 'login' | 'signup';

export function AuthForm() {
    const [mode, setMode] = useState<AuthMode>('login');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [isSubmitting, setIsSubmitting] = useState(false);

    const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        setError(null);

        // Validación para signup
        if (mode === 'signup') {
            if (password !== confirmPassword) {
                setError('Las contraseñas no coinciden');
                return;
            }
            if (password.length < 8) {
                setError('La contraseña debe tener al menos 8 caracteres');
                return;
            }
        }

        setIsSubmitting(true);

        if (mode === 'login') {
            const result = await login(email, password);
            if (!result.success) {
                setError(result.message ?? 'Credenciales inválidas');
                setIsSubmitting(false);
            }
        } else {
            // Signup
            const registerResult = await register(email, password);
            if (!registerResult.success) {
                setError(registerResult.message ?? 'No pudimos crear la cuenta');
                setIsSubmitting(false);
                return;
            }

            // Auto-login después de registro exitoso
            const loginResult = await login(email, password);
            if (!loginResult.success) {
                // Si falla el auto-login, cambiar a modo login
                setMode('login');
                setError('Cuenta creada. Por favor, inicia sesión.');
                setIsSubmitting(false);
            }
        }
    };

    const toggleMode = () => {
        setMode(mode === 'login' ? 'signup' : 'login');
        setError(null);
        setConfirmPassword('');
    };

    return (
        <div className="space-y-6">
            {/* Toggle Tabs */}
            <div className="flex rounded-lg bg-slate-100 p-1">
                <button
                    type="button"
                    onClick={() => setMode('login')}
                    className={cn(
                        'flex-1 rounded-md px-4 py-2 text-sm font-medium transition-all',
                        mode === 'login'
                            ? 'bg-white text-slate-900 shadow-sm'
                            : 'text-slate-600 hover:text-slate-900'
                    )}
                >
                    Ingresar
                </button>
                <button
                    type="button"
                    onClick={() => setMode('signup')}
                    className={cn(
                        'flex-1 rounded-md px-4 py-2 text-sm font-medium transition-all',
                        mode === 'signup'
                            ? 'bg-white text-slate-900 shadow-sm'
                            : 'text-slate-600 hover:text-slate-900'
                    )}
                >
                    Crear cuenta
                </button>
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-5">
                <div className="text-left">
                    <label htmlFor="email" className="text-sm font-medium text-slate-700">
                        Email
                    </label>
                    <input
                        id="email"
                        name="email"
                        type="email"
                        required
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                        className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                        placeholder="tu@empresa.com"
                    />
                </div>

                <div className="text-left">
                    <label htmlFor="password" className="text-sm font-medium text-slate-700">
                        Contraseña
                    </label>
                    <input
                        id="password"
                        name="password"
                        type="password"
                        required
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                        className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                        placeholder="••••••••"
                    />
                </div>

                {mode === 'signup' && (
                    <div className="text-left">
                        <label htmlFor="confirmPassword" className="text-sm font-medium text-slate-700">
                            Repetir contraseña
                        </label>
                        <input
                            id="confirmPassword"
                            name="confirmPassword"
                            type="password"
                            required
                            value={confirmPassword}
                            onChange={(event) => setConfirmPassword(event.target.value)}
                            className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                            placeholder="••••••••"
                        />
                    </div>
                )}

                {error && (
                    <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">
                        {error}
                    </div>
                )}

                <button
                    type="submit"
                    className="w-full rounded-full bg-brand-600 px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-brand-700 disabled:opacity-60"
                    disabled={isSubmitting}
                >
                    {isSubmitting
                        ? mode === 'login'
                            ? 'Ingresando...'
                            : 'Creando cuenta...'
                        : mode === 'login'
                        ? 'Ingresar'
                        : 'Crear cuenta'}
                </button>

                {/* Toggle link */}
                <p className="text-center text-sm text-slate-600">
                    {mode === 'login' ? (
                        <>
                            ¿No tenés cuenta?{' '}
                            <button
                                type="button"
                                onClick={toggleMode}
                                className="font-medium text-brand-600 hover:text-brand-700 hover:underline"
                            >
                                Crear cuenta
                            </button>
                        </>
                    ) : (
                        <>
                            ¿Ya tenés cuenta?{' '}
                            <button
                                type="button"
                                onClick={toggleMode}
                                className="font-medium text-brand-600 hover:text-brand-700 hover:underline"
                            >
                                Ingresar
                            </button>
                        </>
                    )}
                </p>
            </form>
        </div>
    );
}
