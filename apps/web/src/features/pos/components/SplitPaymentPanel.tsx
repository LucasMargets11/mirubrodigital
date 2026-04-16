'use client';

/**
 * SplitPaymentPanel
 *
 * Split-payment UI for POS sales. Allows adding multiple payment lines
 * (each with method, amount, and optional reference). Supports both
 * single and multi-payment flows seamlessly.
 *
 * Features:
 * - Dynamic add/remove payment lines
 * - Auto-fill remaining amount on new lines
 * - Real-time total paid / remaining / excess display
 * - Cash change (vuelto) calculation for efectivo lines
 * - Visual status indicator (exact match, over, under)
 *
 * Accessibility:
 * - Proper field labels and aria attributes
 * - Live region for total status
 */

import { useCallback, useEffect, useId, useState } from 'react';
import { formatCurrency } from '@/features/cash/utils';

// ── Types ──────────────────────────────────────────────────────────────────────

export type UiPaymentMethod =
  | 'efectivo'
  | 'debito'
  | 'credito'
  | 'transferencia'
  | 'mercadopago'
  | 'otro';

export interface PaymentLine {
  id: string;
  method: UiPaymentMethod;
  amount: string;
  reference: string;
  /** true while the amount was set/updated automatically (not manually edited) */
  isAutoAmount: boolean;
}

/** Maps UI payment method → backend Payment.Method choices */
export function toApiPaymentLineMethod(
  m: UiPaymentMethod,
): 'cash' | 'debit' | 'credit' | 'transfer' | 'wallet' | 'account' {
  switch (m) {
    case 'efectivo':
      return 'cash';
    case 'debito':
      return 'debit';
    case 'credito':
      return 'credit';
    case 'transferencia':
      return 'transfer';
    case 'mercadopago':
      return 'wallet';
    case 'otro':
      return 'account';
  }
}

const PAYMENT_METHOD_OPTIONS: { value: UiPaymentMethod; label: string; icon: string }[] = [
  { value: 'efectivo',      label: 'Efectivo',          icon: '💵' },
  { value: 'debito',        label: 'Tarjeta débito',    icon: '💳' },
  { value: 'credito',       label: 'Tarjeta crédito',   icon: '💳' },
  { value: 'transferencia', label: 'Transferencia',     icon: '🏦' },
  { value: 'mercadopago',   label: 'Mercado Pago',      icon: '💙' },
  { value: 'otro',          label: 'Otro',              icon: '•' },
];

// ── Helpers ────────────────────────────────────────────────────────────────────

let lineCounter = 0;
export function createPaymentLine(amount: string = '', method: UiPaymentMethod = 'efectivo'): PaymentLine {
  return { id: `pl-${++lineCounter}`, method, amount, reference: '', isAutoAmount: !amount };
}

// ── Props ──────────────────────────────────────────────────────────────────────

interface SplitPaymentPanelProps {
  lines: PaymentLine[];
  onLinesChange: (lines: PaymentLine[]) => void;
  total: number;
  disabled?: boolean;
  /** Cash received for efectivo lines — used for vuelto calculation */
  cashReceived: string;
  onCashReceivedChange: (v: string) => void;
}

// ── Component ──────────────────────────────────────────────────────────────────

export function SplitPaymentPanel({
  lines,
  onLinesChange,
  total,
  disabled,
  cashReceived,
  onCashReceivedChange,
}: SplitPaymentPanelProps) {
  const uid = useId();

  // ── Derived values ──────────────────────────────────────────────────────

  const totalPaid = lines.reduce((sum, l) => {
    const v = parseFloat(l.amount);
    return sum + (isNaN(v) ? 0 : v);
  }, 0);

  const remaining = Math.max(0, total - totalPaid);
  const excess = Math.max(0, totalPaid - total);
  const isExact = Math.abs(total - totalPaid) < 0.01 && total > 0;

  // Check if any line is cash for vuelto
  const hasCashLine = lines.some((l) => l.method === 'efectivo');
  const cashLineTotal = lines
    .filter((l) => l.method === 'efectivo')
    .reduce((sum, l) => sum + (parseFloat(l.amount) || 0), 0);
  const cashReceivedNum = parseFloat(cashReceived);
  const cashChange = hasCashLine && !isNaN(cashReceivedNum) ? Math.max(0, cashReceivedNum - cashLineTotal) : 0;
  const cashInsufficient = hasCashLine && !isNaN(cashReceivedNum) && cashReceivedNum > 0 && cashReceivedNum < cashLineTotal;

  // ── Cash-change toggle ──────────────────────────────────────────────────

  const [showCashChange, setShowCashChange] = useState(false);

  useEffect(() => {
    if (!hasCashLine) {
      setShowCashChange(false);
      onCashReceivedChange('');
    }
  }, [hasCashLine, onCashReceivedChange]);

  const handleToggleCashChange = useCallback(
    (checked: boolean) => {
      setShowCashChange(checked);
      if (!checked) {
        onCashReceivedChange('');
      }
    },
    [onCashReceivedChange],
  );

  // ── Handlers ────────────────────────────────────────────────────────────

  const updateLine = useCallback(
    (lineId: string, updates: Partial<PaymentLine>) => {
      onLinesChange(lines.map((l) => {
        if (l.id !== lineId) return l;
        // When the user edits the amount, mark it as manual
        const isAmountEdit = 'amount' in updates;
        return { ...l, ...updates, ...(isAmountEdit ? { isAutoAmount: false } : {}) };
      }));
    },
    [lines, onLinesChange],
  );

  const removeLine = useCallback(
    (lineId: string) => {
      const next = lines.filter((l) => l.id !== lineId);
      onLinesChange(next.length === 0 ? [createPaymentLine()] : next);
    },
    [lines, onLinesChange],
  );

  const addLine = useCallback(() => {
    const currentPaid = lines.reduce((sum, l) => sum + (parseFloat(l.amount) || 0), 0);
    const autoAmount = total - currentPaid;
    onLinesChange([
      ...lines,
      createPaymentLine(autoAmount > 0 ? autoAmount.toFixed(2) : ''),
    ]);
  }, [lines, onLinesChange, total]);

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <fieldset>
      <legend className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Pagos
      </legend>

      {/* Payment lines */}
      <div className="space-y-3">
        {lines.map((line, idx) => (
          <div
            key={line.id}
            className="rounded-xl border border-slate-200 bg-white p-3 space-y-2"
          >
            {/* Row 1: Method select + Amount + Remove */}
            <div className="flex items-end gap-2">
              {/* Method */}
              <div className="flex-1 min-w-0">
                <label
                  htmlFor={`${uid}-method-${line.id}`}
                  className="mb-1 block text-xs font-medium text-slate-500"
                >
                  Medio{lines.length > 1 ? ` ${idx + 1}` : ''}
                </label>
                <select
                  id={`${uid}-method-${line.id}`}
                  value={line.method}
                  onChange={(e) => updateLine(line.id, { method: e.target.value as UiPaymentMethod })}
                  disabled={disabled}
                  className="w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-1 focus:ring-slate-300 disabled:opacity-60"
                >
                  {PAYMENT_METHOD_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.icon} {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Amount */}
              <div className="w-36">
                <label
                  htmlFor={`${uid}-amount-${line.id}`}
                  className="mb-1 block text-xs font-medium text-slate-500"
                >
                  Monto a cobrar
                </label>
                <div className="relative">
                  <span
                    className="absolute left-2.5 top-1/2 -translate-y-1/2 text-sm font-medium text-slate-400"
                    aria-hidden
                  >
                    $
                  </span>
                  <input
                    id={`${uid}-amount-${line.id}`}
                    type="number"
                    min={0}
                    step="any"
                    value={line.amount}
                    onChange={(e) => updateLine(line.id, { amount: e.target.value })}
                    disabled={disabled}
                    placeholder="0"
                    className="w-full rounded-lg border border-slate-200 py-2 pl-7 pr-2 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-1 focus:ring-slate-300 disabled:opacity-60 tabular-nums"
                  />
                </div>
              </div>

              {/* Remove button */}
              {lines.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeLine(line.id)}
                  disabled={disabled}
                  aria-label={`Eliminar pago ${idx + 1}`}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 text-slate-400 transition-colors hover:border-rose-200 hover:bg-rose-50 hover:text-rose-500 disabled:opacity-60"
                >
                  <span aria-hidden>✕</span>
                </button>
              )}
            </div>

            {/* Row 2: Reference (optional) */}
            <div>
              <label
                htmlFor={`${uid}-ref-${line.id}`}
                className="mb-1 block text-xs font-medium text-slate-400"
              >
                Referencia <span className="text-slate-300">(opcional)</span>
              </label>
              <input
                id={`${uid}-ref-${line.id}`}
                type="text"
                maxLength={128}
                value={line.reference}
                onChange={(e) => updateLine(line.id, { reference: e.target.value })}
                disabled={disabled}
                placeholder="Nro. operación, alias, últimos 4 dígitos…"
                className="w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm text-slate-700 outline-none focus:border-slate-400 focus:ring-1 focus:ring-slate-300 disabled:opacity-60"
              />
            </div>
          </div>
        ))}
      </div>

      {/* Add another payment line */}
      <button
        type="button"
        onClick={addLine}
        disabled={disabled}
        className="mt-3 w-full rounded-xl border border-dashed border-slate-300 py-2 text-sm font-medium text-slate-500 transition-colors hover:border-slate-400 hover:bg-slate-50 hover:text-slate-700 disabled:opacity-60"
      >
        + Agregar otro medio de pago
      </button>

      {/* Cash: calcular vuelto (only when there's an efectivo line) */}
      {hasCashLine && (
        <div className="mt-4 space-y-3">
          <label className="flex cursor-pointer select-none items-center gap-2">
            <input
              type="checkbox"
              checked={showCashChange}
              onChange={(e) => handleToggleCashChange(e.target.checked)}
              disabled={disabled}
              className="h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-400 disabled:opacity-60"
            />
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Calcular vuelto
            </span>
          </label>

          {showCashChange && (
            <>
              <div>
                <label
                  htmlFor={`${uid}-cash-received`}
                  className="mb-1 block text-xs font-medium text-slate-500"
                >
                  ¿Con cuánto paga?
                </label>
                <div className="relative">
                  <span
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-sm font-medium text-slate-400"
                    aria-hidden
                  >
                    $
                  </span>
                  <input
                    id={`${uid}-cash-received`}
                    type="number"
                    min={0}
                    step="any"
                    placeholder={String(cashLineTotal > 0 ? Math.ceil(cashLineTotal) : '')}
                    value={cashReceived}
                    onChange={(e) => onCashReceivedChange(e.target.value)}
                    disabled={disabled}
                    className="w-full rounded-xl border border-slate-200 py-2.5 pl-8 pr-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-1 focus:ring-slate-300 disabled:opacity-60"
                  />
                </div>
              </div>

              {/* Vuelto inline */}
              {!isNaN(cashReceivedNum) && cashReceivedNum > 0 && !cashInsufficient && cashChange > 0 && (
                <div
                  className="flex items-center justify-between rounded-xl bg-emerald-50 px-4 py-3"
                  aria-live="polite"
                  aria-atomic="true"
                >
                  <span className="text-sm font-medium text-emerald-700">Vuelto</span>
                  <span className="text-lg font-bold text-emerald-800 tabular-nums">
                    {formatCurrency(String(cashChange))}
                  </span>
                </div>
              )}

              {cashInsufficient && (
                <p className="text-xs text-amber-600" aria-live="polite">
                  El monto ingresado no cubre el cobro en efectivo.
                </p>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Summary ────────────────────────────────────────────────────────── */}
      <div
        className={`mt-4 rounded-xl px-4 py-3 ${
          isExact
            ? 'bg-emerald-50 border border-emerald-200'
            : excess > 0
              ? 'bg-rose-50 border border-rose-200'
              : 'bg-slate-50 border border-slate-200'
        }`}
        aria-live="polite"
      >
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium text-slate-600">Total venta</span>
          <span className="font-bold text-slate-900 tabular-nums">{formatCurrency(String(total))}</span>
        </div>
        <div className="mt-1 flex items-center justify-between text-sm">
          <span className={`font-medium ${excess > 0.01 ? 'text-rose-600' : 'text-slate-600'}`}>
            Cobrado
          </span>
          <span className={`font-bold tabular-nums ${excess > 0.01 ? 'text-rose-700' : 'text-slate-900'}`}>
            {formatCurrency(String(totalPaid))}
          </span>
        </div>
        {remaining > 0.01 && (
          <div className="mt-1 flex items-center justify-between text-sm">
            <span className="font-medium text-amber-600">Restante</span>
            <span className="font-bold text-amber-700 tabular-nums">{formatCurrency(String(remaining))}</span>
          </div>
        )}
        {excess > 0.01 && (
          <p className="mt-0.5 text-xs text-rose-500">
            Los montos superan el total por {formatCurrency(String(excess))}
          </p>
        )}
        {cashChange > 0 && (
          <div className="mt-1 flex items-center justify-between text-sm">
            <span className="font-medium text-emerald-600">Vuelto</span>
            <span className="font-bold text-emerald-700 tabular-nums">{formatCurrency(String(cashChange))}</span>
          </div>
        )}
        {isExact && (
          <div className="mt-1 text-center text-xs font-semibold text-emerald-700">
            ✓ Pago completo
          </div>
        )}
      </div>
    </fieldset>
  );
}
