'use client';

import { useState } from 'react';
import type { EmployeeProfile } from '@/types/employees';
import { ROLE_TYPE_LABELS, STATUS_LABELS } from '@/types/employees';
import { employeesApi } from '@/lib/api/employees';
import { ResetPinModalEmployee } from './reset-pin-modal-employee';
import { EmployeeFormModal } from './employee-form-modal';

interface EmployeesTableProps {
  employees: EmployeeProfile[];
  onRefresh: () => void;
}

export function EmployeesTable({ employees, onRefresh }: EmployeesTableProps) {
  const [editTarget, setEditTarget] = useState<EmployeeProfile | null>(null);
  const [pinTarget, setPinTarget] = useState<EmployeeProfile | null>(null);
  const [statusLoading, setStatusLoading] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);

  const handleToggleStatus = async (emp: EmployeeProfile) => {
    if (emp.status === 'active') {
      const confirmed = window.confirm(
        `¿Confirmas suspender a ${emp.alias || `${emp.first_name} ${emp.last_name}`}?\n` +
        'El empleado no podrá iniciar sesión mientras esté suspendido.',
      );
      if (!confirmed) return;
    }
    setStatusLoading(emp.id);
    setStatusError(null);
    try {
      if (emp.status === 'active') {
        await employeesApi.suspend(emp.id);
      } else {
        await employeesApi.reactivate(emp.id);
      }
      onRefresh();
    } catch (err: any) {
      setStatusError(err?.message || 'No se pudo cambiar el estado del empleado.');
    } finally {
      setStatusLoading(null);
    }
  };

  if (employees.length === 0) {
    return (
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-8 text-center">
        <p className="text-sm text-slate-600">No hay empleados operativos registrados.</p>
        <p className="mt-1 text-xs text-slate-500">
          Creá el primer empleado con el botón "+ Nuevo empleado".
        </p>
      </div>
    );
  }

  return (
    <>
      {statusError && (
        <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {statusError}
          <button
            onClick={() => setStatusError(null)}
            className="ml-3 text-red-500 hover:text-red-700 font-medium"
          >
            Cerrar
          </button>
        </div>
      )}
      <div className="overflow-hidden rounded-lg border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                Empleado
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                Código
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                Rol
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                Estado
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                Credencial
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wide text-slate-500">
                Acciones
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 bg-white">
            {employees.map((emp) => (
              <tr key={emp.id}>
                {/* Name */}
                <td className="px-4 py-3">
                  <div>
                    <p className="text-sm font-medium text-slate-900">
                      {emp.first_name} {emp.last_name}
                    </p>
                    {emp.alias && (
                      <p className="text-xs text-slate-500">{emp.alias}</p>
                    )}
                  </div>
                </td>

                {/* Code */}
                <td className="px-4 py-3">
                  <span className="font-mono text-sm text-slate-700">{emp.employee_code}</span>
                </td>

                {/* Role */}
                <td className="px-4 py-3">
                  <span className="text-sm text-slate-700">
                    {ROLE_TYPE_LABELS[emp.role_type] ?? emp.role_type_display}
                  </span>
                </td>

                {/* Status */}
                <td className="px-4 py-3">
                  <EmployeeStatusBadge status={emp.status} mustChangePin={emp.must_change_pin} />
                </td>

                {/* Credential type */}
                <td className="px-4 py-3 text-sm text-slate-600">{emp.credential_type_display}</td>

                {/* Actions */}
                <td className="px-4 py-3 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={() => setPinTarget(emp)}
                      className="rounded-md border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors"
                    >
                      Reset PIN
                    </button>
                    <button
                      onClick={() => setEditTarget(emp)}
                      className="rounded-md border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors"
                    >
                      Editar
                    </button>
                    <button
                      disabled={statusLoading === emp.id}
                      onClick={() => handleToggleStatus(emp)}
                      className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                        emp.status === 'active'
                          ? 'border border-amber-200 text-amber-700 hover:bg-amber-50'
                          : 'border border-green-200 text-green-700 hover:bg-green-50'
                      } disabled:opacity-50`}
                    >
                      {statusLoading === emp.id
                        ? '...'
                        : emp.status === 'active'
                        ? 'Suspender'
                        : 'Reactivar'}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editTarget && (
        <EmployeeFormModal
          isOpen
          mode="edit"
          employee={editTarget}
          onClose={() => {
            setEditTarget(null);
            onRefresh();
          }}
        />
      )}

      {pinTarget && (
        <ResetPinModalEmployee
          isOpen
          employee={pinTarget}
          onClose={() => setPinTarget(null)}
        />
      )}
    </>
  );
}

function EmployeeStatusBadge({
  status,
  mustChangePin,
}: {
  status: EmployeeProfile['status'];
  mustChangePin: boolean;
}) {
  const map: Record<EmployeeProfile['status'], string> = {
    active:    'bg-green-50 text-green-700 border-green-200',
    inactive:  'bg-slate-100 text-slate-600 border-slate-200',
    suspended: 'bg-red-50 text-red-700 border-red-200',
  };
  return (
    <div className="flex flex-col gap-1">
      <span
        className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${map[status]}`}
      >
        {STATUS_LABELS[status]}
      </span>
      {mustChangePin && (
        <span className="text-xs text-amber-600">⚠ Debe cambiar PIN</span>
      )}
    </div>
  );
}
