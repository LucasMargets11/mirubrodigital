'use client';

/**
 * PosRecentSales
 *
 * Shows the most recent sales (up to 5) for the employee's current open
 * cash session. Designed for the POS terminal home page.
 *
 * Only renders when a cash session is open. Handles loading, empty, and error states.
 */

import { usePosCashCurrentSales } from '@/features/pos/cash-hooks';
import { usePosCashCurrentSession } from '@/features/pos/cash-hooks';
import { formatCurrency } from '@/features/cash/utils';
import type { PosCashSessionSale } from '@/types/pos-cash';

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatTime(isoString: string): string {
  return new Date(isoString).toLocaleTimeString('es-AR', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'America/Argentina/Buenos_Aires',
  });
}

// ── Sale row ──────────────────────────────────────────────────────────────────

function SaleRow({ sale }: { sale: PosCashSessionSale }) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5">
      <div className="flex items-center gap-3 min-w-0">
        <span
          className={`h-2 w-2 shrink-0 rounded-full ${
            sale.status === 'completed' ? 'bg-emerald-500' : 'bg-gray-400'
          }`}
          aria-hidden
        />
        <div className="min-w-0">
          <p className="text-sm font-medium text-slate-900">
            Venta #{sale.number}
          </p>
          <p className="text-xs text-slate-500">
            {sale.items_count} {sale.items_count === 1 ? 'ítem' : 'ítems'}
            {' · '}
            {sale.payment_method_label}
          </p>
        </div>
      </div>
      <div className="ml-3 shrink-0 text-right">
        <p className="text-sm font-semibold text-slate-900">
          {formatCurrency(sale.total)}
        </p>
        <p className="text-xs text-slate-400">{formatTime(sale.created_at)}</p>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function PosRecentSales() {
  const { session } = usePosCashCurrentSession();
  const { data, isLoading, isError } = usePosCashCurrentSales();

  // Don't render if there's no open session
  if (!session) return null;

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
        Ventas recientes de esta caja
      </p>

      {isLoading ? (
        <p className="text-xs text-slate-400">Cargando ventas…</p>
      ) : isError ? (
        <p className="text-xs text-rose-500">
          No se pudieron cargar las ventas. Intentá de nuevo.
        </p>
      ) : data && data.sales.length > 0 ? (
        <div className="divide-y divide-slate-100 rounded-xl border border-slate-100 bg-white">
          {data.sales.map((sale) => (
            <SaleRow key={sale.id} sale={sale} />
          ))}
        </div>
      ) : (
        <p className="text-xs text-slate-400">
          Todavía no hay ventas en esta sesión.
        </p>
      )}
    </div>
  );
}
