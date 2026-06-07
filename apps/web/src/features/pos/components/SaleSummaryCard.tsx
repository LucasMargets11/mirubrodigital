'use client';

/**
 * SaleSummaryCard
 *
 * Sticky summary panel: subtotal, discount, total, confirm/cancel actions.
 *
 * Accessibility:
 * - Uses <dl> for key/value summary pairs.
 * - Confirm button is disabled with aria-disabled when there's nothing to submit.
 * - Error shown with role="alert".
 * - Total uses aria-live="polite" so screen readers announce changes.
 */

import { formatCurrency } from '@/features/cash/utils';

interface SaleSummaryCardProps {
  subtotal: number;
  discountAmount: number;
  total: number;
  onConfirm: () => void;
  onCancel: () => void;
  isPending: boolean;
  /** Disable confirm (e.g. cart empty, validation issues) */
  disabled: boolean;
  /** Error message from the API or local validation */
  error: string;
  /** Success message after confirmed */
  successMsg: string;
  confirmLabel?: string;
  pendingLabel?: string;
  helperText?: string;
}

export function SaleSummaryCard({
  subtotal,
  discountAmount,
  total,
  onConfirm,
  onCancel,
  isPending,
  disabled,
  error,
  successMsg,
  confirmLabel = 'Confirmar venta',
  pendingLabel = 'Confirmando…',
  helperText,
}: SaleSummaryCardProps) {
  return (
    <div className="rounded-2xl bg-slate-900 p-5 text-white">
      {/* Success feedback */}
      {successMsg && (
        <div
          role="status"
          aria-live="assertive"
          className="mb-4 rounded-xl bg-emerald-500/20 px-4 py-3 text-center text-sm font-semibold text-emerald-300"
        >
          ✓ {successMsg}
        </div>
      )}

      {/* Summary */}
      <dl className="space-y-2 text-sm">
        <div className="flex justify-between">
          <dt className="text-slate-400">Subtotal</dt>
          <dd className="font-medium tabular-nums">{formatCurrency(String(subtotal))}</dd>
        </div>

        {discountAmount > 0 && (
          <div className="flex justify-between text-emerald-400">
            <dt>Descuento</dt>
            <dd className="tabular-nums">− {formatCurrency(String(discountAmount))}</dd>
          </div>
        )}

        <div className="mt-1 border-t border-slate-700 pt-3 flex items-baseline justify-between">
          <dt className="text-base font-semibold text-slate-300">Total</dt>
          <dd
            className="text-2xl font-bold tabular-nums"
            aria-live="polite"
            aria-atomic="true"
            aria-label={`Total: ${formatCurrency(String(total))}`}
          >
            {formatCurrency(String(total))}
          </dd>
        </div>
      </dl>

      {helperText && (
        <p className="mt-4 rounded-xl bg-slate-800 px-4 py-3 text-sm text-slate-300">
          {helperText}
        </p>
      )}

      {/* Error */}
      {error && (
        <p
          role="alert"
          className="mt-4 rounded-xl bg-rose-900/40 px-4 py-2.5 text-sm text-rose-300"
        >
          {error}
        </p>
      )}

      {/* Actions */}
      <div className="mt-5 space-y-2">
        <button
          type="button"
          onClick={onConfirm}
          disabled={disabled || isPending}
          aria-disabled={disabled || isPending}
          className="w-full rounded-xl bg-white py-3 text-sm font-bold text-slate-900 transition-colors hover:bg-slate-100 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-slate-900"
        >
          {isPending ? pendingLabel : confirmLabel}
        </button>

        <button
          type="button"
          onClick={onCancel}
          disabled={isPending}
          className="w-full rounded-xl border border-slate-700 py-2.5 text-sm font-medium text-slate-400 transition-colors hover:border-slate-600 hover:text-slate-300 disabled:opacity-50"
        >
          Cancelar
        </button>
      </div>
    </div>
  );
}
