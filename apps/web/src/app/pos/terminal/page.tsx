'use client';

/**
 * Main operative terminal shell — /pos/terminal
 *
 * Shows:
 * - Employee identity card (name, role, branch)
 * - Cash POS section (open/active session, movements, close)
 * - Recent sales for the current cash session
 * - Logout button
 *
 * Only reachable after successful login + no pending PIN change.
 */

import { useEmployeeSession } from '@/features/pos/context';
import { PosCashSection } from '@/features/pos/components/PosCashSection';
import { PosRecentSales } from '@/features/pos/components/PosRecentSales';

// ── Terminal page ─────────────────────────────────────────────────────────────

export default function PosTerminalPage() {
  const { session, logout } = useEmployeeSession();

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

      {/* Recent sales for the current cash session */}
      <div className="mb-6">
        <PosRecentSales />
      </div>
    </div>
  );
}
