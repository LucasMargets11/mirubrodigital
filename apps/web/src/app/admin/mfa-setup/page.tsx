'use client';

import { useState, useEffect } from 'react';
import { Shield, Check, Copy, Loader2, AlertTriangle } from 'lucide-react';

import { adminMFAEnroll, adminMFAConfirm, type AdminMFAEnrollResult } from '@/lib/admin/client';

type Step = 'loading' | 'enroll' | 'confirm' | 'done';

export default function AdminMFASetupPage() {
  const [step, setStep] = useState<Step>('loading');
  const [enrollData, setEnrollData] = useState<Extract<AdminMFAEnrollResult, { status: 'ok' }> | null>(null);
  const [otpCode, setOtpCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [copied, setCopied] = useState<'secret' | 'codes' | null>(null);

  useEffect(() => {
    const startEnroll = async () => {
      const result = await adminMFAEnroll();
      if (result.status === 'error') {
        setError(result.message);
        setStep('enroll');
        return;
      }
      setEnrollData(result);
      setStep('enroll');
    };
    startEnroll();
  }, []);

  const handleConfirm = async () => {
    setError(null);
    setIsSubmitting(true);
    const result = await adminMFAConfirm(otpCode);
    setIsSubmitting(false);

    if (result.status === 'error') {
      setError(result.message);
      setOtpCode('');
      return;
    }

    setStep('done');
  };

  const copyToClipboard = async (text: string, label: 'secret' | 'codes') => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(label);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      // Clipboard API not available
    }
  };

  if (step === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-12">
      <div className="w-full max-w-lg space-y-8">
        {/* Header */}
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600">
            <Shield className="h-7 w-7 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">Configurar MFA</h1>
          <p className="mt-1 text-sm text-slate-400">
            La autenticación de dos factores es obligatoria para acceder al panel admin
          </p>
        </div>

        {error && (
          <div className="flex items-start gap-3 rounded-xl border border-red-900/50 bg-red-950/50 p-4">
            <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-400" />
            <p className="text-sm text-red-300">{error}</p>
          </div>
        )}

        {/* Enrollment Step */}
        {step === 'enroll' && enrollData && (
          <div className="space-y-6">
            {/* QR/Secret */}
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
              <h2 className="text-sm font-semibold text-white">1. Escaneá el código QR</h2>
              <p className="text-xs text-slate-400">
                Abrí tu app de autenticación (Google Authenticator, Authy, 1Password) y escaneá
                este código, o ingresá la clave manualmente:
              </p>
              {/* Manual secret */}
              <div className="flex items-center gap-2">
                <code className="flex-1 rounded-lg bg-slate-800 px-3 py-2 font-mono text-xs text-indigo-300 break-all">
                  {enrollData.secret}
                </code>
                <button
                  type="button"
                  onClick={() => copyToClipboard(enrollData.secret, 'secret')}
                  className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-white"
                >
                  {copied === 'secret' ? <Check className="h-4 w-4 text-green-400" /> : <Copy className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {/* Recovery Codes */}
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
              <h2 className="text-sm font-semibold text-white">2. Guardá tus códigos de recuperación</h2>
              <p className="text-xs text-slate-400">
                Si perdés acceso a tu app de autenticación, podés usar estos códigos de un solo uso.
                Guardalos en un lugar seguro.
              </p>
              <div className="grid grid-cols-2 gap-2">
                {enrollData.recovery_codes.map((code, i) => (
                  <code key={i} className="rounded-lg bg-slate-800 px-3 py-2 text-center font-mono text-xs text-amber-300">
                    {code}
                  </code>
                ))}
              </div>
              <button
                type="button"
                onClick={() => copyToClipboard(enrollData.recovery_codes.join('\n'), 'codes')}
                className="flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800"
              >
                {copied === 'codes' ? <Check className="h-3 w-3 text-green-400" /> : <Copy className="h-3 w-3" />}
                Copiar códigos
              </button>
            </div>

            {/* Confirm */}
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
              <h2 className="text-sm font-semibold text-white">3. Confirmá con un código OTP</h2>
              <p className="text-xs text-slate-400">
                Ingresá el código de 6 dígitos que muestra tu app para confirmar la configuración.
              </p>
              <div className="flex gap-3">
                <input
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  className="flex-1 rounded-xl border border-slate-700 bg-slate-800 px-4 py-3 text-center font-mono text-lg tracking-[0.3em] text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  placeholder="000000"
                />
                <button
                  type="button"
                  onClick={handleConfirm}
                  disabled={isSubmitting || otpCode.length !== 6}
                  className="rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Confirmar'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Done */}
        {step === 'done' && (
          <div className="rounded-xl border border-green-900/50 bg-green-950/50 p-8 text-center space-y-4">
            <Check className="mx-auto h-12 w-12 text-green-400" />
            <h2 className="text-lg font-bold text-white">MFA activado correctamente</h2>
            <p className="text-sm text-slate-300">
              A partir de ahora necesitarás tu app de autenticación para iniciar sesión.
            </p>
            <button
              type="button"
              onClick={() => window.location.assign('/admin/dashboard')}
              className="mt-4 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-500"
            >
              Ir al Dashboard
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
