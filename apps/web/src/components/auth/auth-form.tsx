'use client';

declare global {
    interface Window {
        google?: {
            accounts: {
                id: {
                    initialize: (config: Record<string, unknown>) => void;
                    renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void;
                    prompt: () => void;
                };
            };
        };
    }
}

import { FormEvent, useState, useCallback, useEffect, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import { login, register, googleAuth, googlePreauthorizedLogin } from '@/lib/auth/client';
import { cn } from '@/lib/utils';

type AuthMode = 'login' | 'signup';
type GoogleEndpoint = 'standard' | 'preauthorized';

type AuthFormProps = {
    googleEndpoint?: GoogleEndpoint;
    googleOnly?: boolean;
};

/* ── Google "G" icon (official multi-color) ─────────────────────────────── */
function GoogleIcon({ className }: { className?: string }) {
    return (
        <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
            <path
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
                fill="#4285F4"
            />
            <path
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                fill="#34A853"
            />
            <path
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                fill="#FBBC05"
            />
            <path
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                fill="#EA4335"
            />
        </svg>
    );
}

export function AuthForm({ googleEndpoint = 'standard', googleOnly = false }: AuthFormProps = {}) {
    const searchParams = useSearchParams();
    const next = searchParams.get('next') ?? undefined;
    const isGoogleOnlyBeta = process.env.NEXT_PUBLIC_AUTH_BETA_GOOGLE_ONLY === 'true';

    // ADMIN-CLIENTES 04D: the admin-generated access link may carry a
    // business_id that targets the exact Business the owner should enter.
    // Read it from the query string, validate it as a positive integer, and
    // forward it to the preauthorized login. It is never used as authorization
    // on its own — the backend re-validates it against the Google user's own
    // active owner Memberships. Malformed values are dropped (undefined).
    const rawBusinessId = searchParams.get('business_id');
    const businessId = (() => {
        const parsed = Number(rawBusinessId);
        return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
    })();

    const [mode, setMode] = useState<AuthMode>('login');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [showInternalLogin, setShowInternalLogin] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);
    const [isSubmitting, setIsSubmitting] = useState(false);

    // ── Google Identity Services ────────────────────────────────────────
    const googleWrapperRef = useRef<HTMLDivElement>(null);
    const googleBtnRef = useRef<HTMLDivElement>(null);
    const googleRequestInFlightRef = useRef(false);
    const [googleReady, setGoogleReady] = useState(false);
    const [googleRendered, setGoogleRendered] = useState(false);
    const [containerWidth, setContainerWidth] = useState(0);

    const handleGoogleResponse = useCallback(
        async (response: { credential: string }) => {
            if (googleRequestInFlightRef.current) return;
            googleRequestInFlightRef.current = true;
            setError(null);
            setSuccessMessage(null);
            setIsSubmitting(true);
            try {
                const authenticate = googleEndpoint === 'preauthorized'
                    ? googlePreauthorizedLogin
                    : googleAuth;
                const result = googleEndpoint === 'preauthorized' && businessId !== undefined
                    ? await googlePreauthorizedLogin(response.credential, businessId)
                    : await authenticate(response.credential);
                if (!result.success) {
                    setError(result.message ?? 'No pudimos autenticar con Google');
                    return;
                }
                if (result.onboarding) {
                    window.location.assign(next ?? '/app/onboarding');
                } else {
                    window.location.assign('/app/dashboard');
                }
            } finally {
                googleRequestInFlightRef.current = false;
                setIsSubmitting(false);
            }
        },
        [googleEndpoint, next, businessId],
    );

    useEffect(() => {
        const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_OAUTH_CLIENT_ID;
        if (!GOOGLE_CLIENT_ID) return;

        if (document.getElementById('gsi-script')) {
            if (window.google?.accounts?.id) setGoogleReady(true);
            return;
        }

        const script = document.createElement('script');
        script.id = 'gsi-script';
        script.src = 'https://accounts.google.com/gsi/client';
        script.async = true;
        script.defer = true;
        script.onload = () => setGoogleReady(true);
        document.head.appendChild(script);
    }, []);

    // ── Measure Google wrapper width ────────────────────────────────────
    useEffect(() => {
        const el = googleWrapperRef.current;
        if (!el) return;
        const ro = new ResizeObserver((entries) => {
            const w = Math.floor(entries[0].contentRect.width);
            if (w > 0) setContainerWidth(w);
        });
        ro.observe(el);
        return () => ro.disconnect();
    }, []);

    useEffect(() => {
        const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_OAUTH_CLIENT_ID;
        if (!googleReady || !GOOGLE_CLIENT_ID || !googleBtnRef.current || containerWidth <= 0) return;
        if (!window.google?.accounts?.id) return;

        window.google.accounts.id.initialize({
            client_id: GOOGLE_CLIENT_ID,
            callback: handleGoogleResponse,
            auto_select: false,
            cancel_on_tap_outside: true,
        });

        const target = googleBtnRef.current;
        while (target.firstChild) target.removeChild(target.firstChild);

        window.google.accounts.id.renderButton(target, {
            type: 'standard',
            shape: 'pill',
            theme: 'outline',
            size: 'large',
            text: 'continue_with',
            width: containerWidth,
            locale: 'es',
        });

        requestAnimationFrame(() => setGoogleRendered(true));
    }, [googleReady, containerWidth, handleGoogleResponse]);

    // ── Form handlers ───────────────────────────────────────────────────

    const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        setError(null);
        setSuccessMessage(null);

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
            const result = await login(email, password, next);
            if (!result.success) {
                setError(result.message ?? 'Credenciales inválidas');
                setIsSubmitting(false);
            }
        } else {
            const registerResult = await register(email, password);
            if (!registerResult.success) {
                setError(registerResult.message ?? 'No pudimos crear la cuenta');
                setIsSubmitting(false);
                return;
            }
            setSuccessMessage(`Te enviamos un email de verificación a ${email}`);
            const loginResult = await login(email, password, next);
            if (!loginResult.success) {
                setMode('login');
                setError('Cuenta creada. Por favor, inicia sesión.');
                setSuccessMessage(null);
                setIsSubmitting(false);
            }
        }
    };

    const handleInternalLoginSubmit = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        setError(null);
        setSuccessMessage(null);

        if (!email || !password) {
            setError('Completá email/usuario y contraseña');
            return;
        }

        setIsSubmitting(true);
        const result = await login(email, password, next);
        if (!result.success) {
            setError(result.message ?? 'Credenciales inválidas');
            setIsSubmitting(false);
        }
    };

    const switchMode = (target: AuthMode) => {
        setMode(target);
        setError(null);
        setSuccessMessage(null);
        setConfirmPassword('');
    };

    const showPasswordUi = !isGoogleOnlyBeta || showInternalLogin;

    // ── Render ──────────────────────────────────────────────────────────

    const googleSignIn = (
        <div ref={googleWrapperRef} className="relative">
            <button
                type="button"
                disabled={isSubmitting}
                aria-busy={isSubmitting}
                onClick={() => {
                    if (!googleRendered && !process.env.NEXT_PUBLIC_GOOGLE_OAUTH_CLIENT_ID) {
                        setError('Acceso con Google no disponible');
                    }
                }}
                className="w-full flex items-center justify-center gap-3 rounded-lg border border-slate-200 bg-white px-6 py-2.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:ring-offset-2 disabled:opacity-60"
            >
                {isSubmitting ? (
                    <span
                        aria-hidden="true"
                        className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600"
                    />
                ) : (
                    <GoogleIcon className="h-5 w-5 shrink-0" />
                )}
                {isSubmitting ? 'Ingresando...' : 'Continuar con Google'}
            </button>

            <div
                ref={googleBtnRef}
                className={cn(
                    'absolute inset-0 w-full overflow-hidden opacity-0 [&>div]:w-full [&>div]:h-full [&_iframe]:w-full [&_iframe]:h-full',
                    googleRendered && !isSubmitting ? 'pointer-events-auto' : 'pointer-events-none',
                )}
            />
        </div>
    );

    if (googleOnly) {
        return (
            <div className="mx-auto w-full max-w-[400px] space-y-4">
                {googleSignIn}
                {error && (
                    <div role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">
                        {error}
                    </div>
                )}
            </div>
        );
    }

    return (
        <div className="mx-auto w-full max-w-[400px] space-y-5">
            {isGoogleOnlyBeta && (
                <>
                    {googleSignIn}

                    {!showInternalLogin && (
                        <div className="rounded-lg border border-slate-200 bg-slate-50/60 px-4 py-3">
                            <p className="text-xs text-slate-600">
                                ¿Tenés una cuenta interna o demo?
                            </p>
                            <button
                                type="button"
                                onClick={() => {
                                    setShowInternalLogin(true);
                                    setMode('login');
                                    setError(null);
                                    setSuccessMessage(null);
                                }}
                                className="mt-2 text-sm font-medium text-slate-700 underline underline-offset-4 hover:text-slate-900"
                            >
                                Ingreso interno/demo
                            </button>
                        </div>
                    )}
                </>
            )}

            {showPasswordUi && (
                <>
                    {!isGoogleOnlyBeta && (
                        <div className="flex rounded-xl bg-slate-100/80 p-1">
                            <button
                                type="button"
                                onClick={() => switchMode('login')}
                                className={cn(
                                    'flex-1 rounded-lg px-4 py-2.5 text-sm font-medium transition-all',
                                    mode === 'login'
                                        ? 'bg-white text-slate-900 shadow-sm'
                                        : 'text-slate-500 hover:text-slate-700',
                                )}
                            >
                                Ingresar
                            </button>
                            <button
                                type="button"
                                onClick={() => switchMode('signup')}
                                className={cn(
                                    'flex-1 rounded-lg px-4 py-2.5 text-sm font-medium transition-all',
                                    mode === 'signup'
                                        ? 'bg-white text-slate-900 shadow-sm'
                                        : 'text-slate-500 hover:text-slate-700',
                                )}
                            >
                                Crear cuenta
                            </button>
                        </div>
                    )}

                    {isGoogleOnlyBeta && (
                        <form onSubmit={handleInternalLoginSubmit} className="space-y-3.5 rounded-lg border border-slate-200 bg-white p-4">
                            <div className="flex items-center justify-between">
                                <p className="text-sm font-medium text-slate-700">Ingreso interno/demo</p>
                                <button
                                    type="button"
                                    onClick={() => {
                                        setShowInternalLogin(false);
                                        setEmail('');
                                        setPassword('');
                                        setError(null);
                                    }}
                                    className="text-xs text-slate-500 hover:text-slate-700"
                                >
                                    Ocultar
                                </button>
                            </div>

                            <div>
                                <label htmlFor="email" className="block text-sm font-medium text-slate-700">
                                    Email o usuario
                                </label>
                                <input
                                    id="email"
                                    name="email"
                                    type="text"
                                    required
                                    value={email}
                                    onChange={(event) => setEmail(event.target.value)}
                                    className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                                    placeholder="tu@empresa.com o usuario"
                                />
                            </div>

                            <div>
                                <label htmlFor="password" className="block text-sm font-medium text-slate-700">
                                    Contraseña
                                </label>
                                <input
                                    id="password"
                                    name="password"
                                    type="password"
                                    required
                                    value={password}
                                    onChange={(event) => setPassword(event.target.value)}
                                    className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
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
                                className="w-full rounded-lg bg-brand-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm shadow-brand-600/20 transition-colors hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:ring-offset-2 disabled:opacity-60"
                                disabled={isSubmitting}
                            >
                                {isSubmitting ? 'Ingresando...' : 'Ingresar con contraseña'}
                            </button>
                        </form>
                    )}

                    {!isGoogleOnlyBeta && (
                        <>
                            <form onSubmit={handleSubmit} className="space-y-3.5">
                                <div>
                                    <label htmlFor="email" className="block text-sm font-medium text-slate-700">
                                        {mode === 'login' ? 'Email o usuario' : 'Email'}
                                    </label>
                                    <input
                                        id="email"
                                        name="email"
                                        type={mode === 'signup' ? 'email' : 'text'}
                                        required
                                        value={email}
                                        onChange={(event) => setEmail(event.target.value)}
                                        className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                                        placeholder={mode === 'login' ? 'tu@empresa.com o usuario' : 'tu@empresa.com'}
                                    />
                                </div>

                                <div>
                                    <label htmlFor="password" className="block text-sm font-medium text-slate-700">
                                        Contraseña
                                    </label>
                                    <input
                                        id="password"
                                        name="password"
                                        type="password"
                                        required
                                        value={password}
                                        onChange={(event) => setPassword(event.target.value)}
                                        className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                                        placeholder="••••••••"
                                    />
                                </div>

                                {mode === 'signup' && (
                                    <div>
                                        <label htmlFor="confirmPassword" className="block text-sm font-medium text-slate-700">
                                            Repetir contraseña
                                        </label>
                                        <input
                                            id="confirmPassword"
                                            name="confirmPassword"
                                            type="password"
                                            required
                                            value={confirmPassword}
                                            onChange={(event) => setConfirmPassword(event.target.value)}
                                            className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                                            placeholder="••••••••"
                                        />
                                    </div>
                                )}

                                {mode === 'login' && (
                                    <div className="flex justify-end">
                                        <a
                                            href="/olvidar-contrasena"
                                            className="text-[13px] text-slate-400 transition-colors hover:text-brand-600"
                                        >
                                            ¿Olvidaste tu contraseña?
                                        </a>
                                    </div>
                                )}

                                {error && (
                                    <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">
                                        {error}
                                    </div>
                                )}

                                {successMessage && !error && (
                                    <div className="rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                                        {successMessage}
                                    </div>
                                )}

                                <button
                                    type="submit"
                                    className="w-full rounded-lg bg-brand-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm shadow-brand-600/20 transition-colors hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:ring-offset-2 disabled:opacity-60"
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

                                {mode === 'signup' && (
                                    <p className="text-center text-[13px] text-slate-400">
                                        Te vamos a enviar un correo de verificación
                                    </p>
                                )}
                            </form>

                            <div className="flex items-center gap-4">
                                <div className="h-px flex-1 bg-slate-200" />
                                <span className="text-[13px] text-slate-400 select-none">
                                    o continuá con
                                </span>
                                <div className="h-px flex-1 bg-slate-200" />
                            </div>

                            {googleSignIn}
                        </>
                    )}
                </>
            )}
        </div>
    );
}
