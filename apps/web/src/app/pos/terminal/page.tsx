'use client';

/**
 * Main operative terminal shell — /pos/terminal
 *
 * Shows:
 * - Employee identity card (name, role, branch)
 * - Cash POS section (open/active session, movements, close)
 * - Capabilities grid (which POS actions are enabled)
 * - Logout button
 *
 * Only reachable after successful login + no pending PIN change.
 */

import { useEmployeeSession } from '@/features/pos/context';
import { usePosCapabilities } from '@/features/pos/hooks';
import { PosCashSection } from '@/features/pos/components/PosCashSection';
import type { PosCapabilitySet } from '@/types/employees';

// ── Capability labels ─────────────────────────────────────────────────────────

const CAPABILITY_LABELS: Record<keyof PosCapabilitySet, string> = {
  can_open_pos: 'Abrir POS',
  can_view_assigned_branch: 'Ver sucursal asignada',
  can_create_sale: 'Crear venta',
  can_refund_sale: 'Realizar devolución',
  can_manage_cash: 'Gestionar caja',
  can_view_reports: 'Ver reportes',
  can_manage_employees_pos: 'Gestionar empleados en POS',
  can_open_cash: 'Abrir sesión de caja',
  can_close_cash: 'Cerrar sesión de caja',
  can_register_cash_movement: 'Registrar movimiento de caja',
};

function CapabilityBadge({
  label,
  enabled,
}: {
  label: string;
  enabled: boolean;
}) {
  return (
    <div
      className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
        enabled
          ? 'bg-green-50 text-green-700'
          : 'bg-gray-50 text-gray-400 line-through'
      }`}
    >
      <span
        className={`h-2 w-2 shrink-0 rounded-full ${enabled ? 'bg-green-500' : 'bg-gray-300'}`}
        aria-hidden
      />
      {label}
    </div>
  );
}

// ── Terminal page ─────────────────────────────────────────────────────────────

export default function PosTerminalPage() {
  const { session, logout } = useEmployeeSession();
  const { capabilities, roleType, isLoading: capsLoading, error: capsError } =
    usePosCapabilities();

  if (session.status !== 'authenticated') {
    // Layout guard should have redirected already; render nothing here
    return null;
  }

  const { employee } = session;

  const ROLE_LABELS: Record<string, string> = {
    manager_op: 'Gerente Operativo',
    cashier: 'Cajero',
    server: 'Mesero',
    kitchen: 'Cocina',
    delivery: 'Repartidor',
  };

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">Terminal Operativo</h1>
        <button
          onClick={logout}
          className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100"
        >
          Cerrar sesión
        </button>
      </div>

      {/* Employee card */}
      <div className="mb-6 rounded-2xl bg-white p-6 shadow-sm">
        <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
          Empleado activo
        </p>
        <h2 className="mt-1 text-2xl font-bold text-gray-900">
          {employee.display_name}
        </h2>
        <p className="text-sm text-gray-500">{employee.full_name}</p>

        <div className="mt-4 flex flex-wrap gap-4 text-sm text-gray-600">
          <span>
            <span className="font-medium">Código:</span>{' '}
            {employee.employee_code}
          </span>
          <span>
            <span className="font-medium">Rol:</span>{' '}
            {ROLE_LABELS[employee.role_type] ?? employee.role_type}
          </span>
          {employee.branch_name && (
            <span>
              <span className="font-medium">Sucursal:</span>{' '}
              {employee.branch_name}
            </span>
          )}
          <span>
            <span className="font-medium">Negocio:</span>{' '}
            {employee.business_name}
          </span>
        </div>
      </div>

      {/* Cash section — only visible to roles with cash capabilities */}
      <div className="mb-6">
        <PosCashSection />
      </div>

      {/* Capabilities */}
      <div className="rounded-2xl bg-white p-6 shadow-sm">
        <h3 className="mb-4 text-sm font-semibold text-gray-700">
          Permisos operativos
          {roleType && (
            <span className="ml-2 font-normal text-gray-400">
              ({ROLE_LABELS[roleType] ?? roleType})
            </span>
          )}
        </h3>

        {capsLoading && (
          <p className="text-sm text-gray-400">Cargando permisos…</p>
        )}

        {capsError && (
          <p className="text-sm text-red-500">
            No se pudieron cargar los permisos. Intenta recargar la página.
          </p>
        )}

        {capabilities && (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {(Object.keys(CAPABILITY_LABELS) as Array<keyof PosCapabilitySet>).map(
              (key) => (
                <CapabilityBadge
                  key={key}
                  label={CAPABILITY_LABELS[key]}
                  enabled={capabilities[key]}
                />
              ),
            )}
          </div>
        )}
      </div>
    </div>
  );
}
