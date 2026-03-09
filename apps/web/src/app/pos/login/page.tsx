'use client';

/**
 * Operative employee login page — /pos/login
 *
 * Fields: business_id (number), employee_code (string), pin (string)
 * On success: context.login() stores token + hydrates session.
 * If must_change_pin: layout guard redirects to /pos/change-pin automatically.
 * Otherwise: redirects to /pos/terminal.
 */

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ApiError } from '@/lib/api/client';
import { useEmployeeSession } from '@/features/pos/context';

export default function PosLoginPage() {
  const { login, session } = useEmployeeSession();
  const router = useRouter();

  const [businessId, setBusinessId] = useState('');
  const [employeeCode, setEmployeeCode] = useState('');
  const [pin, setPin] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      await login({
        business_id: parseInt(businessId, 10),
        employee_code: employeeCode.trim(),
        pin,
      });
      // Guard in layout.tsx handles the must_change_pin redirect.
      // When session is clean, send to terminal.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      router.replace('/pos/terminal' as any);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 429) {
          setError('Demasiados intentos. Espera un momento antes de volver a intentarlo.');
        } else if (err.status === 401 || err.status === 400) {
          setError('Código de empleado o PIN incorrecto.');
        } else {
          setError(err.message);
        }
      } else {
        setError('Error de conexión. Verifica la red e intenta de nuevo.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  const isLoading = session.status === 'loading' || submitting;

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-md">
        <h1 className="mb-6 text-center text-2xl font-semibold text-gray-900">
          Acceso Operativo
        </h1>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div>
            <label
              htmlFor="business_id"
              className="block text-sm font-medium text-gray-700"
            >
              ID de negocio
            </label>
            <input
              id="business_id"
              type="number"
              required
              min={1}
              value={businessId}
              onChange={(e) => setBusinessId(e.target.value)}
              placeholder="123"
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              disabled={isLoading}
              autoComplete="off"
            />
          </div>

          <div>
            <label
              htmlFor="employee_code"
              className="block text-sm font-medium text-gray-700"
            >
              Código de empleado
            </label>
            <input
              id="employee_code"
              type="text"
              required
              value={employeeCode}
              onChange={(e) => setEmployeeCode(e.target.value)}
              placeholder="EMP-001"
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              disabled={isLoading}
              autoComplete="username"
            />
          </div>

          <div>
            <label
              htmlFor="pin"
              className="block text-sm font-medium text-gray-700"
            >
              PIN
            </label>
            <input
              id="pin"
              type="password"
              required
              minLength={4}
              maxLength={8}
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              placeholder="••••"
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              disabled={isLoading}
              autoComplete="current-password"
              inputMode="numeric"
            />
          </div>

          {error && (
            <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isLoading ? 'Verificando…' : 'Ingresar'}
          </button>
        </form>
      </div>
    </div>
  );
}
