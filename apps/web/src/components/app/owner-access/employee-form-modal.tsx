'use client';

import { useState } from 'react';
import { employeesApi } from '@/lib/api/employees';
import type {
  CreateEmployeePayload,
  EmployeeProfile,
  EmployeeRoleType,
  UpdateEmployeePayload,
} from '@/types/employees';
import { ROLE_TYPE_LABELS } from '@/types/employees';

type Mode = 'create' | 'edit';

interface EmployeeFormModalProps {
  isOpen: boolean;
  mode: Mode;
  employee?: EmployeeProfile;
  onClose: (created?: EmployeeProfile) => void;
}

const ROLE_OPTIONS: { value: EmployeeRoleType; label: string }[] = Object.entries(
  ROLE_TYPE_LABELS,
).map(([value, label]) => ({ value: value as EmployeeRoleType, label }));

export function EmployeeFormModal({
  isOpen,
  mode,
  employee,
  onClose,
}: EmployeeFormModalProps) {
  const [firstName, setFirstName]   = useState(employee?.first_name ?? '');
  const [lastName, setLastName]     = useState(employee?.last_name ?? '');
  const [alias, setAlias]           = useState(employee?.alias ?? '');
  const [roleType, setRoleType]     = useState<EmployeeRoleType>(
    employee?.role_type ?? 'cashier',
  );
  const [initialPin, setInitialPin] = useState('');
  const [isLoading, setIsLoading]   = useState(false);
  const [error, setError]           = useState<string | null>(null);

  /** After creation, show the PIN once */
  const [createdEmployee, setCreatedEmployee] = useState<EmployeeProfile | null>(null);
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const title = mode === 'create' ? 'Nuevo Empleado Operativo' : 'Editar Empleado';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      if (mode === 'create') {
        const payload: CreateEmployeePayload = {
          first_name: firstName.trim(),
          last_name:  lastName.trim(),
          alias:      alias.trim() || undefined,
          role_type:  roleType,
          ...(initialPin ? { initial_pin: initialPin } : {}),
        };
        const result = await employeesApi.create(payload);
        setCreatedEmployee(result);
      } else if (employee) {
        const payload: UpdateEmployeePayload = {
          first_name: firstName.trim(),
          last_name:  lastName.trim(),
          alias:      alias.trim() || undefined,
          role_type:  roleType,
        };
        await employeesApi.update(employee.id, payload);
        onClose();
      }
    } catch (err: any) {
      setError(err.message || 'Ocurrió un error. Intentá de nuevo.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopyPin = async () => {
    if (createdEmployee?.initial_pin) {
      await navigator.clipboard.writeText(createdEmployee.initial_pin);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDone = () => {
    onClose(createdEmployee ?? undefined);
  };

  // ── Post-creation PIN reveal ──────────────────────────────────────────────
  if (createdEmployee) {
    const displayName =
      createdEmployee.alias ||
      `${createdEmployee.first_name} ${createdEmployee.last_name}`.trim();
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
        <div className="w-full max-w-md rounded-xl bg-white shadow-2xl">
          <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
            <h2 className="text-lg font-semibold text-slate-900">Empleado creado</h2>
          </div>
          <div className="space-y-4 px-6 py-5">
            <div className="rounded-lg border border-green-200 bg-green-50 p-4">
              <p className="text-sm font-medium text-green-800">
                ✓ {displayName} fue creado exitosamente.
              </p>
              <p className="mt-0.5 font-mono text-xs text-green-700">
                {createdEmployee.employee_code}
              </p>
            </div>

            {createdEmployee.initial_pin && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                <p className="text-sm font-medium text-amber-800">
                  PIN inicial (mostralo solo una vez):
                </p>
                <div className="mt-3 flex items-center gap-3">
                  <span className="flex-1 rounded border border-amber-200 bg-white px-3 py-2 text-center font-mono text-2xl font-bold tracking-widest text-slate-900 select-all">
                    {createdEmployee.initial_pin}
                  </span>
                  <button
                    onClick={handleCopyPin}
                    className="rounded-lg border border-amber-200 px-3 py-2 text-sm font-medium text-amber-700 hover:bg-amber-100 transition-colors"
                  >
                    {copied ? '✓ Copiado' : 'Copiar'}
                  </button>
                </div>
                <p className="mt-2 text-xs text-amber-700">
                  El empleado deberá cambiarlo en su próximo inicio de sesión.
                </p>
              </div>
            )}

            <button
              onClick={handleDone}
              className="w-full rounded-lg bg-slate-800 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-700 transition-colors"
            >
              Listo
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Form ──────────────────────────────────────────────────────────────────
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <div className="w-full max-w-lg rounded-xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
          <button
            onClick={() => onClose()}
            className="rounded p-1 text-slate-400 hover:text-slate-600 transition-colors"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 px-6 py-5">
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700">
                Nombre <span className="text-red-500">*</span>
              </label>
              <input
                required
                type="text"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700">
                Apellido <span className="text-red-500">*</span>
              </label>
              <input
                required
                type="text"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700">
              Alias (nombre en pantallas operativas)
            </label>
            <input
              type="text"
              placeholder="Ej: Ana, El Chino, …"
              value={alias}
              onChange={(e) => setAlias(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700">
              Rol operativo <span className="text-red-500">*</span>
            </label>
            <select
              required
              value={roleType}
              onChange={(e) => setRoleType(e.target.value as EmployeeRoleType)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              {ROLE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {mode === 'create' && (
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700">
                PIN inicial (opcional)
              </label>
              <input
                type="tel"
                inputMode="numeric"
                placeholder="Dejar vacío para generar automáticamente"
                maxLength={8}
                value={initialPin}
                onChange={(e) =>
                  setInitialPin(e.target.value.replace(/\D/g, '').slice(0, 8))
                }
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              <p className="mt-1 text-xs text-slate-500">
                Mínimo 4 dígitos. Si lo dejás vacío, se genera automáticamente.
              </p>
            </div>
          )}

          <div className="flex items-center justify-end gap-3 border-t border-slate-200 pt-4">
            <button
              type="button"
              onClick={() => onClose()}
              className="rounded-lg px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-100 transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {isLoading
                ? mode === 'create' ? 'Creando…' : 'Guardando…'
                : mode === 'create' ? 'Crear empleado' : 'Guardar cambios'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
