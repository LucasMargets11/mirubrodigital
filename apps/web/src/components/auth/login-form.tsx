'use client';

import { FormEvent, useState } from 'react';

import { login } from '@/lib/auth/client';

export function LoginForm() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [isSubmitting, setIsSubmitting] = useState(false);

    const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        setError(null);
        setIsSubmitting(true);
        const result = await login(email, password);
        if (!result.success) {
            setError(result.message ?? 'Credenciales inválidas');
            setIsSubmitting(false);
        }
    };

    return (
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
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 focus:border-brand-500 focus:outline-none"
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
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 focus:border-brand-500 focus:outline-none"
                    placeholder="••••••••"
                />
            </div>
            {error ? <p className="text-sm text-red-500">{error}</p> : null}
            <button
                type="submit"
                className="w-full rounded-full bg-brand-600 px-6 py-3 text-sm font-semibold text-white disabled:opacity-60"
                disabled={isSubmitting}
            >
                {isSubmitting ? 'Iniciando sesión...' : 'Entrar'}
            </button>
        </form>
    );
}
