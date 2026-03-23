'use client';

import { FormEvent, useState, useRef, useEffect } from 'react';
import { Shield, Loader2, AlertTriangle, KeyRound, ArrowLeft } from 'lucide-react';

import {
  adminLogin,
  adminMFAVerify,
  adminMFARecovery,
  type AdminLoginResult,
} from '@/lib/admin/client';

type Step = 'credentials' | 'mfa' | 'recovery';

export default function AdminLoginPage() {
  const [step, setStep] = useState<Step>('credentials');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mfaToken, setMfaToken] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [recoveryCode, setRecoveryCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [retryAfter, setRetryAfter] = useState<number | null>(null);
  const otpRef = useRef<HTMLInputElement>(null);

  // Auto-focus OTP input when entering MFA step
  useEffect(() => {
    if (step === 'mfa' && otpRef.current) {
      otpRef.current.focus();
    }
  }, [step]);

  // Countdown timer for retry-after
  useEffect(() => {
    if (retryAfter === null || retryAfter <= 0) return;
    const timer = setInterval(() => {
      setRetryAfter((prev) => (prev && prev > 1 ? prev - 1 : null));
    }, 1000);
    return () => clearInterval(timer);
  }, [retryAfter]);

  const handleCredentials = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    const result = await adminLogin(email, password);
    setIsSubmitting(false);

    if (result.status === 'error') {
      setError(result.message);
      if (result.retry_after) setRetryAfter(result.retry_after);
      return;
    }

    if (result.status === 'mfa_required') {
      setMfaToken(result.mfa_token);
      setStep('mfa');
      return;
    }

    // Login complete (bootstrap mode) — redirect to admin
    if (!result.mfa_enrolled) {
      window.location.assign('/admin/mfa-setup');
    } else {
      window.location.assign('/admin/dashboard');
    }
  };

  const handleMFA = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    const result = await adminMFAVerify(mfaToken, otpCode);
    setIsSubmitting(false);

    if (result.status === 'error') {
      setError(result.message);
      if (result.retry_after) setRetryAfter(result.retry_after);
      setOtpCode('');
      return;
    }

    window.location.assign('/admin/dashboard');
  };

  const handleRecovery = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    const result = await adminMFARecovery(mfaToken, recoveryCode);
    setIsSubmitting(false);

    if (result.status === 'error') {
      setError(result.message);
      return;
    }

    window.location.assign('/admin/dashboard');
  };

  const isDisabled = isSubmitting || (retryAfter !== null && retryAfter > 0);

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-md space-y-8">
        {/* Header */}
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600">
            <Shield className="h-7 w-7 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">Mi Rubro Admin</h1>
          <p className="mt-1 text-sm text-slate-400">Panel interno de administración</p>
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-start gap-3 rounded-xl border border-red-900/50 bg-red-950/50 p-4">
            <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-400" />
            <p className="text-sm text-red-300">{error}</p>
          </div>
        )}

        {/* Retry countdown */}
        {retryAfter !== null && retryAfter > 0 && (
          <div className="rounded-xl border border-amber-900/50 bg-amber-950/50 p-4 text-center">
            <p className="text-sm text-amber-300">
              Reintentá en <span className="font-mono font-bold">{retryAfter}s</span>
            </p>
          </div>
        )}

        {/* Step 1: Credentials */}
        {step === 'credentials' && (
          <form onSubmit={handleCredentials} className="space-y-5">
            <div>
              <label htmlFor="admin-email" className="block text-sm font-medium text-slate-300">
                Email
              </label>
              <input
                id="admin-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                placeholder="admin@mirubro.com"
                disabled={isDisabled}
              />
            </div>
            <div>
              <label htmlFor="admin-password" className="block text-sm font-medium text-slate-300">
                Contraseña
              </label>
              <input
                id="admin-password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                disabled={isDisabled}
              />
            </div>
            <button
              type="submit"
              disabled={isDisabled}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSubmitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                'Iniciar sesión'
              )}
            </button>
          </form>
        )}

        {/* Step 2: MFA OTP */}
        {step === 'mfa' && (
          <form onSubmit={handleMFA} className="space-y-5">
            <div className="text-center">
              <KeyRound className="mx-auto h-10 w-10 text-indigo-400" />
              <p className="mt-3 text-sm text-slate-300">
                Ingresá el código de tu app de autenticación
              </p>
            </div>
            <div>
              <input
                ref={otpRef}
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={6}
                required
                autoComplete="one-time-code"
                value={otpCode}
                onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                className="w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-4 text-center font-mono text-2xl tracking-[0.5em] text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                placeholder="000000"
                disabled={isDisabled}
              />
            </div>
            <button
              type="submit"
              disabled={isDisabled || otpCode.length !== 6}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Verificar'}
            </button>
            <div className="flex items-center justify-between text-sm">
              <button
                type="button"
                onClick={() => { setStep('recovery'); setError(null); }}
                className="text-slate-400 hover:text-white"
              >
                Usar código de recuperación
              </button>
              <button
                type="button"
                onClick={() => { setStep('credentials'); setError(null); setOtpCode(''); }}
                className="flex items-center gap-1 text-slate-400 hover:text-white"
              >
                <ArrowLeft className="h-3 w-3" /> Volver
              </button>
            </div>
          </form>
        )}

        {/* Step 2 (alt): Recovery Code */}
        {step === 'recovery' && (
          <form onSubmit={handleRecovery} className="space-y-5">
            <div className="text-center">
              <p className="text-sm text-slate-300">
                Ingresá uno de tus códigos de recuperación
              </p>
            </div>
            <div>
              <input
                type="text"
                maxLength={16}
                required
                value={recoveryCode}
                onChange={(e) => setRecoveryCode(e.target.value.toUpperCase())}
                className="w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-4 text-center font-mono text-lg tracking-wider text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                placeholder="XXXX1234"
                disabled={isDisabled}
              />
            </div>
            <button
              type="submit"
              disabled={isDisabled || !recoveryCode.trim()}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Recuperar acceso'}
            </button>
            <button
              type="button"
              onClick={() => { setStep('mfa'); setError(null); }}
              className="flex w-full items-center justify-center gap-1 text-sm text-slate-400 hover:text-white"
            >
              <ArrowLeft className="h-3 w-3" /> Volver a código OTP
            </button>
          </form>
        )}

        <p className="text-center text-xs text-slate-600">
          Acceso restringido a personal autorizado de Mi Rubro
        </p>
      </div>
    </div>
  );
}
