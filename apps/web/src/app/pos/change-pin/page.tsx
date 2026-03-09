'use client';

/**
 * Mandatory PIN change page — /pos/change-pin
 *
 * Accessible when must_change_pin=true (and also voluntarily for PIN rotation).
 * On success: context updates mustChangePin→false, redirects to /pos/terminal.
 * On bad_current_pin error: shows inline field error.
 */

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ApiError } from '@/lib/api/client';
import { isBadCurrentPin } from '@/lib/api/pos';
import { useEmployeeSession } from '@/features/pos/context';

export default function PosChangePinPage() {
  const { changePin, session } = useEmployeeSession();
  const router = useRouter();

  const [currentPin, setCurrentPin] = useState('');
  const [newPin, setNewPin] = useState('');
  const [confirmPin, setConfirmPin] = useState('');

  const [fieldError, setFieldError] = useState<{
    current?: string;
    new?: string;
    confirm?: string;
    general?: string;
  }>({});

  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  const isMandatory =
    session.status === 'authenticated' && session.mustChangePin;

  function validate(): boolean {
    const errors: typeof fieldError = {};

    if (!currentPin) {
      errors.current = 'Ingresa tu PIN actual';
    }
    if (!newPin) {
      errors.new = 'Ingresa el nuevo PIN';
    } else if (!/^\d{4,8}$/.test(newPin)) {
      errors.new = 'El PIN debe tener entre 4 y 8 dígitos numéricos';
    } else if (newPin === currentPin) {
      errors.new = 'El nuevo PIN no puede ser igual al actual';
    }
    if (!confirmPin) {
      errors.confirm = 'Confirma el nuevo PIN';
    } else if (newPin && confirmPin !== newPin) {
      errors.confirm = 'Los PINes no coinciden';
    }

    setFieldError(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFieldError({});

    if (!validate()) return;

    setSubmitting(true);

    try {
      await changePin({
        current_pin: currentPin,
        new_pin: newPin,
        confirm_new_pin: confirmPin,
      });

      setSuccess(true);

      // After a brief acknowledgement pause, move to terminal
      setTimeout(() => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        router.replace('/pos/terminal' as any);
      }, 1200);
    } catch (err) {
      if (isBadCurrentPin(err)) {
        setFieldError({ current: 'PIN actual incorrecto' });
      } else if (err instanceof ApiError && err.status === 400) {
        setFieldError({
          general: 'El PIN no cumple los requisitos. Usa entre 4 y 8 dígitos.',
        });
      } else {
        setFieldError({
          general:
            err instanceof Error
              ? err.message
              : 'Error al cambiar el PIN. Intenta de nuevo.',
        });
      }
    } finally {
      setSubmitting(false);
    }
  }

  const isLoading = submitting;

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-md">
        <h1 className="mb-2 text-center text-2xl font-semibold text-gray-900">
          Cambiar PIN
        </h1>

        {isMandatory && (
          <p className="mb-6 rounded-lg bg-amber-50 px-3 py-2 text-center text-sm text-amber-700">
            Debes cambiar tu PIN antes de continuar.
          </p>
        )}

        {success ? (
          <p
            role="status"
            className="rounded-lg bg-green-50 px-3 py-3 text-center text-sm font-medium text-green-700"
          >
            PIN actualizado correctamente. Redirigiendo…
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div>
              <label
                htmlFor="current_pin"
                className="block text-sm font-medium text-gray-700"
              >
                PIN actual
              </label>
              <input
                id="current_pin"
                type="password"
                required
                minLength={4}
                maxLength={8}
                value={currentPin}
                onChange={(e) => setCurrentPin(e.target.value)}
                placeholder="••••"
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                disabled={isLoading}
                autoComplete="current-password"
                inputMode="numeric"
              />
              {fieldError.current && (
                <p className="mt-1 text-xs text-red-600">{fieldError.current}</p>
              )}
            </div>

            <div>
              <label
                htmlFor="new_pin"
                className="block text-sm font-medium text-gray-700"
              >
                Nuevo PIN
              </label>
              <input
                id="new_pin"
                type="password"
                required
                minLength={4}
                maxLength={8}
                value={newPin}
                onChange={(e) => setNewPin(e.target.value)}
                placeholder="••••"
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                disabled={isLoading}
                autoComplete="new-password"
                inputMode="numeric"
              />
              {fieldError.new && (
                <p className="mt-1 text-xs text-red-600">{fieldError.new}</p>
              )}
            </div>

            <div>
              <label
                htmlFor="confirm_pin"
                className="block text-sm font-medium text-gray-700"
              >
                Confirmar nuevo PIN
              </label>
              <input
                id="confirm_pin"
                type="password"
                required
                minLength={4}
                maxLength={8}
                value={confirmPin}
                onChange={(e) => setConfirmPin(e.target.value)}
                placeholder="••••"
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                disabled={isLoading}
                autoComplete="new-password"
                inputMode="numeric"
              />
              {fieldError.confirm && (
                <p className="mt-1 text-xs text-red-600">{fieldError.confirm}</p>
              )}
            </div>

            {fieldError.general && (
              <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
                {fieldError.general}
              </p>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isLoading ? 'Guardando…' : 'Cambiar PIN'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
