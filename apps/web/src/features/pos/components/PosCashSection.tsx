'use client';

/**
 * PosCashSection
 *
 * Self-contained cash section for the POS terminal page.
 *
 * Behaviour:
 * - Reads capabilities from usePosCapabilities hook.
 * - If the employee has no cash capabilities → renders nothing.
 * - Fetches current session via usePosCashCurrentSession.
 * - Shows the appropriate UI depending on session state.
 * - All API calls use X-Employee-Token; admin auth is never touched.
 */

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { usePosCapabilities } from '@/features/pos/hooks';
import {
  usePosCashCurrentSession,
} from '@/features/pos/cash-hooks';
import { PosOpenCashModal } from './PosOpenCashModal';
import { PosMovementModal } from './PosMovementModal';
import { PosCloseCashModal } from './PosCloseCashModal';
import { formatCurrency, formatDateTime } from '@/features/cash/utils';

// ── Helpers ───────────────────────────────────────────────────────────────────

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-bold text-slate-900">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function PosCashSection() {
  const { capabilities, isLoading: capsLoading } = usePosCapabilities();
  const { session, isLoading: sessionLoading, refetch } = usePosCashCurrentSession();
  const router = useRouter();

  const [openModalOpen, setOpenModalOpen] = useState(false);
  const [movementModalOpen, setMovementModalOpen] = useState(false);
  const [closeModalOpen, setCloseModalOpen] = useState(false);

  // Don't render anything until capabilities have loaded
  if (capsLoading) return null;

  // If the employee doesn't have any cash capability, hide this section entirely
  const canOpen = capabilities?.can_open_cash ?? false;
  const canClose = capabilities?.can_close_cash ?? false;
  const canMovement = capabilities?.can_register_cash_movement ?? false;
  const canCreateSale = capabilities?.can_create_sale ?? false;
  const hasCashAccess = canOpen || canClose || canMovement || canCreateSale;

  if (!hasCashAccess) return null;

  // ── Loading skeleton ───────────────────────────────────────────────────────
  if (sessionLoading) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Caja</p>
        <p className="mt-2 text-sm text-slate-400">Cargando estado de caja…</p>
      </div>
    );
  }

  // ── No open session ────────────────────────────────────────────────────────
  if (!session) {
    return (
      <>
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-center shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Caja</p>
          <h3 className="mt-1 text-xl font-semibold text-slate-900">Sin caja abierta</h3>
          <p className="mt-1 text-sm text-slate-500">
            Abrí una sesión para registrar cobros y movimientos de efectivo.
          </p>

          {canOpen ? (
            <button
              type="button"
              onClick={() => setOpenModalOpen(true)}
              className="mt-4 inline-flex items-center justify-center rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white hover:bg-slate-700"
            >
              Abrir caja
            </button>
          ) : (
            <p className="mt-3 text-xs text-slate-400">
              Tu rol no permite abrir la caja.
            </p>
          )}
        </div>

        <PosOpenCashModal
          open={openModalOpen}
          onClose={() => setOpenModalOpen(false)}
          onAlreadyOpen={() => void refetch()}
        />
      </>
    );
  }

  // ── Active session ─────────────────────────────────────────────────────────
  const totals = session.totals;

  return (
    <>
      <div className="rounded-2xl border border-emerald-200 bg-gradient-to-br from-emerald-50 to-white p-6 shadow-sm space-y-5">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-emerald-600">
              Caja abierta
            </p>
            <h3 className="mt-0.5 text-xl font-bold text-slate-900">
              Apertura {formatCurrency(session.opening_cash_amount)}
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              {formatDateTime(session.opened_at)}
              {session.opened_by_name ? ` · ${session.opened_by_name}` : ''}
            </p>
          </div>

          {/* Actions */}
          <div className="flex shrink-0 flex-wrap gap-2">
            {canCreateSale && (
              <button
                type="button"
                onClick={() => router.push('/pos/terminal/new-sale' as any)}
                className="rounded-full bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-700"
              >
                + Venta
              </button>
            )}
            {canMovement && (
              <button
                type="button"
                onClick={() => setMovementModalOpen(true)}
                className="rounded-full border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                + Movimiento
              </button>
            )}
            {canClose && (
              <button
                type="button"
                onClick={() => setCloseModalOpen(true)}
                className="rounded-full border border-rose-300 px-3 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-50"
              >
                Cerrar caja
              </button>
            )}
          </div>
        </div>

        {/* Totals grid */}
        {totals && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard
              label="Efectivo esperado"
              value={formatCurrency(totals.cash_expected_total)}
              sub="Referencia de cierre"
            />
            <StatCard
              label="Ventas"
              value={formatCurrency(totals.total_sales)}
              sub="Cobradas en sesión"
            />
            <StatCard
              label="Ingresos"
              value={formatCurrency(totals.total_in)}
            />
            <StatCard
              label="Egresos"
              value={formatCurrency(totals.total_out)}
            />
          </div>
        )}

        {/* ID badge */}
        <p className="text-right text-xs text-slate-300">
          Sesión {session.id.slice(0, 8)}…
        </p>
      </div>

      <PosMovementModal
        open={movementModalOpen}
        onClose={() => setMovementModalOpen(false)}
      />

      <PosCloseCashModal
        open={closeModalOpen}
        session={session}
        onClose={() => {
          setCloseModalOpen(false);
          void refetch();
        }}
      />
    </>
  );
}
