'use client';

import { useState } from 'react';
import { employeesApi } from '@/lib/api/employees';
import type { EmployeeProfile } from '@/types/employees';
import { ROLE_TYPE_LABELS } from '@/types/employees';

interface ResetPinModalEmployeeProps {
  isOpen: boolean;
  employee: EmployeeProfile;
  onClose: () => void;
}

export function ResetPinModalEmployee({
  isOpen,
  employee,
  onClose,
}: ResetPinModalEmployeeProps) {
  const [customPin, setCustomPin]     = useState('');
  const [isLoading, setIsLoading]     = useState(false);
  const [error, setError]             = useState<string | null>(null);
  const [temporaryPin, setTemporaryPin] = useState<string | null>(null);
  const [copied, setCopied]           = useState(false);

  if (!isOpen) return null;

  const handleReset = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const resp = await employeesApi.resetPin(
        employee.id,
        customPin ? { new_pin: customPin } : {},
      );
      setTemporaryPin(resp.temporary_pin);
    } catch (err: any) {
      setError(err.message || 'Error al resetear el PIN.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopy = async () => {
    if (temporaryPin) {
      await navigator.clipboard.writeText(temporaryPin);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleClose = () => {
    setCustomPin('');
    setTemporaryPin(null);
    setError(null);
    setCopied(false);
    onClose();
  };

  const displayName = employee.alias || `${employee.first_name} ${employee.last_name}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <div className="w-full max-w-md rounded-xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-slate-900">Resetear PIN</h2>
          <button
            onClick={handleClose}
            className="rounded p-1 text-slate-400 hover:text-slate-600 transition-colors"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-5 px-6 py-5">
          {/* Employee info */}
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <p className="text-sm font-medium text-slate-900">{displayName}</p>
            <p className="mt-0.5 font-mono text-xs text-slate-500">{employee.employee_code}</p>
            <p className="text-xs text-slate-500">
              {ROLE_TYPE_LABELS[employee.role_type] ?? employee.role_type_display}
            </p>
          </div>

          {/* Result */}
          {temporaryPin ? (
            <div className="space-y-3">
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                <p className="text-sm font-medium text-amber-800">
                  PIN temporal generado — mostralo solo una vez:
                </p>
                <div className="mt-3 flex items-center gap-3">
                  <span className="flex-1 rounded border border-amber-200 bg-white px-3 py-2 text-center font-mono text-2xl font-bold tracking-widest text-slate-900 select-all">
                    {temporaryPin}
                  </span>
                  <button
                    onClick={handleCopy}
                    className="rounded-lg border border-amber-200 px-3 py-2 text-sm font-medium text-amber-700 hover:bg-amber-100 transition-colors"
                  >
                    {copied ? '✓ Copiado' : 'Copiar'}
                  </button>
                </div>
                <p className="mt-2 text-xs text-amber-700">
                  El empleado deberá cambiarlo en su próximo inicio de sesión.
                </p>
              </div>
              <button
                onClick={handleClose}
                className="w-full rounded-lg bg-slate-800 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-700 transition-colors"
              >
                Listo
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {error && (
                <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                  {error}
                </div>
              )}

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  Nuevo PIN (opcional)
                </label>
                <input
                  type="tel"
                  inputMode="numeric"
                  placeholder="Dejar vacío para generar automáticamente"
                  maxLength={8}
                  value={customPin}
                  onChange={(e) =>
                    setCustomPin(e.target.value.replace(/\D/g, '').slice(0, 8))
                  }
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                <p className="mt-1 text-xs text-slate-500">
                  Mínimo 4 dígitos. Si lo dejás vacío, se genera un PIN aleatorio.
                </p>
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  onClick={handleClose}
                  className="rounded-lg px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-100 transition-colors"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleReset}
                  disabled={isLoading || (!!customPin && customPin.length < 4)}
                  className="rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
                >
                  {isLoading ? 'Reseteando…' : 'Resetear PIN'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
